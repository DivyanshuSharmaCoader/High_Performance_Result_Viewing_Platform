import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Browser, type BrowserContext, type Locator, type Page } from "@playwright/test";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const TRAINING = path.resolve(HERE, "../../docs/training");
const DURATIONS: Record<string, Record<string, number>> = JSON.parse(
  fs.readFileSync(path.join(TRAINING, "SCRIPTS/durations.json"), "utf8"),
);
export const OUT = path.resolve(HERE, "../test-results/training");
const STATE = path.join(OUT, "state.json");

/** The fictional school used throughout the series (names, addresses and marks are made up). */
export const SCHOOL = {
  name: "Sunrise Public School",
  ownerName: "Sunita Sharma",
  ownerEmail: "sunita.sharma@sunrise-school.example",
  // Test-only passwords for the throwaway recording stack; never used anywhere real.
  ownerPassword: "sunrise-training-owner-2026",
  teacherName: "Amit Kumar",
  teacherEmail: "amit.kumar@sunrise-school.example",
  teacherPassword: "sunrise-training-teacher-2026",
  student: { enrollment: "SPS1001", name: "Aarav Sharma", password: "aarav-training-2026" },
};

export function saveState(values: Record<string, string>): void {
  fs.mkdirSync(OUT, { recursive: true });
  const now = fs.existsSync(STATE) ? JSON.parse(fs.readFileSync(STATE, "utf8")) : {};
  fs.writeFileSync(STATE, JSON.stringify({ ...now, ...values }, null, 1));
}

export function state(): Record<string, string> {
  return JSON.parse(fs.readFileSync(STATE, "utf8"));
}

// A pointer the viewer can follow (a recording has no mouse cursor) and a box around what's next.
const POINTER = `
(() => {
  if (window.__scPoint) return;
  const style = document.createElement('style');
  style.textContent = '#sc-pointer{position:fixed;z-index:2147483647;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;background:rgba(234,88,12,.85);box-shadow:0 0 0 4px rgba(234,88,12,.25);pointer-events:none;transition:left .6s ease,top .6s ease}' +
    '#sc-box{position:fixed;z-index:2147483646;border:3px solid #ea580c;border-radius:8px;pointer-events:none;transition:all .25s ease;opacity:0}';
  const add = () => {
    document.head.appendChild(style);
    const p = document.createElement('div'); p.id = 'sc-pointer'; p.style.left = '60%'; p.style.top = '40%';
    const b = document.createElement('div'); b.id = 'sc-box';
    document.body.append(p, b);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add();
  window.__scPoint = (x, y, w, h) => {
    const p = document.getElementById('sc-pointer'), b = document.getElementById('sc-box');
    if (!p || !b) return;
    p.style.left = (x + w / 2) + 'px'; p.style.top = (y + h / 2) + 'px';
    Object.assign(b.style, { left: (x - 6) + 'px', top: (y - 6) + 'px', width: (w + 12) + 'px', height: (h + 12) + 'px', opacity: '1' });
    clearTimeout(window.__scHide); window.__scHide = setTimeout(() => { b.style.opacity = '0'; }, 1800);
  };
})();`;

/** One module's recording: a fresh browser window, its video, and when each narrated beat started. */
export class Lesson {
  private t0 = 0;
  private timeline: { id: string; at: number }[] = [];
  private readonly beats: Record<string, number>;

  private constructor(
    readonly id: string,
    readonly context: BrowserContext,
    readonly page: Page,
  ) {
    const beats = DURATIONS[id];
    if (!beats) throw new Error(`no narration durations for ${id}: run build.py narrate`);
    this.beats = beats;
    this.t0 = Date.now();
  }

  static async start(browser: Browser, id: string): Promise<Lesson> {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 810 },
      recordVideo: { dir: path.join(OUT, "raw", id), size: { width: 1440, height: 810 } }, // scaled to 1080p later
      locale: "en-IN",
      timezoneId: "Asia/Kolkata",
    });
    await context.addInitScript(POINTER);
    const page = await context.newPage(); // the video starts with this page
    return new Lesson(id, context, page);
  }

  /** Narrate a beat: it starts now, the action runs while it is spoken, and the next beat waits for it. */
  async beat(id: string, action?: () => Promise<void>): Promise<void> {
    const needs = this.beats[id];
    if (needs === undefined) throw new Error(`${this.id}: no beat "${id}" in the script`);
    if (this.timeline.some((t) => t.id === id)) throw new Error(`${this.id}: beat "${id}" used twice`);
    const started = Date.now();
    this.timeline.push({ id, at: started - this.t0 });
    if (action) await action();
    const left = needs - (Date.now() - started);
    if (left > 0) await this.page.waitForTimeout(left);
  }

  async point(target: Locator): Promise<void> {
    await target.scrollIntoViewIfNeeded({ timeout: 20_000 });
    const box = await target.boundingBox();
    if (box) {
      await this.page.evaluate(
        (b) =>
          (window as unknown as { __scPoint?: (...a: number[]) => void }).__scPoint?.(
            b.x,
            b.y,
            b.width,
            b.height,
          ),
        box,
      );
      await this.page.waitForTimeout(900);
    }
  }

  async click(target: Locator): Promise<void> {
    await this.point(target);
    await target.click();
  }

  async type(target: Locator, text: string): Promise<void> {
    await this.point(target);
    await target.click();
    await target.fill("");
    await target.pressSequentially(text, { delay: 55 });
  }

  async choose(target: Locator, option: string | { label: string }): Promise<void> {
    await this.point(target);
    await target.selectOption(option);
  }

  /** Pick the option whose text contains ``text`` (option labels often add the code or session). */
  async chooseContaining(target: Locator, text: string): Promise<void> {
    await this.point(target);
    const options = await target.locator("option").allTextContents();
    const match = options.find((o) => o.includes(text));
    if (!match) throw new Error(`no option containing "${text}" in ${JSON.stringify(options)}`);
    await target.selectOption({ label: match });
  }

  /** Upload a file through the page's own file picker button. */
  async upload(button: Locator, name: string, text: string): Promise<void> {
    await this.point(button);
    const chooser = this.page.waitForEvent("filechooser");
    await button.click();
    await (await chooser).setFiles({ name, mimeType: "text/csv", buffer: Buffer.from(text) });
  }

  /** Close the window (the video is written), keep it as OUT/<id>.webm with OUT/<id>.timeline.json. */
  async finish(): Promise<void> {
    await this.page.waitForTimeout(1200);
    const video = this.page.video();
    await this.context.close();
    fs.mkdirSync(OUT, { recursive: true });
    if (video) fs.copyFileSync(await video.path(), path.join(OUT, `${this.id}.webm`));
    fs.writeFileSync(path.join(OUT, `${this.id}.timeline.json`), JSON.stringify(this.timeline, null, 1));
    const missing = Object.keys(this.beats).filter((b) => !this.timeline.some((t) => t.id === b));
    expect(missing, `${this.id}: beats in the script but not recorded`).toEqual([]);
  }
}
