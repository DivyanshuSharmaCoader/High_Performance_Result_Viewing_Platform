import { useCallback, useEffect, useState } from "react";

export interface BrandTokens {
  primary: string;
  primary_contrast: string;
  primary_ink: string;
  accent: string;
  accent_contrast?: string;
  font_family: string;
}

const HEX = /^#[0-9a-f]{6}$/i;
const FONTS = new Set(["Inter", "Source Sans 3", "Noto Sans", "IBM Plex Sans", "Merriweather Sans"]);

/**
 * Apply tenant brand tokens to :root. Only validated hex colours and allow-listed fonts are applied,
 * so tenant configuration can never inject CSS.
 */
export function applyBrandTokens(tokens: BrandTokens, root: HTMLElement = document.documentElement): void {
  const set = (name: string, value: string | undefined) => {
    if (value && HEX.test(value)) root.style.setProperty(name, value);
  };
  set("--sc-brand", tokens.primary);
  set("--sc-brand-contrast", tokens.primary_contrast);
  set("--sc-brand-ink-light", tokens.primary_ink);
  set("--sc-accent", tokens.accent);
  if (FONTS.has(tokens.font_family)) {
    root.style.setProperty(
      "--sc-font-family",
      tokens.font_family === "Inter" ? '"Inter Variable"' : `"${tokens.font_family}"`,
    );
  }
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta && HEX.test(tokens.primary)) meta.setAttribute("content", tokens.primary);
}

export type ColorScheme = "light" | "dark" | "system";
const STORAGE_KEY = "sc-color-scheme";

function resolve(scheme: ColorScheme): "light" | "dark" {
  if (scheme !== "system") return scheme;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyColorScheme(scheme: ColorScheme): void {
  document.documentElement.classList.toggle("dark", resolve(scheme) === "dark");
}

export function readColorScheme(): ColorScheme {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "light" || v === "dark" || v === "system" ? v : "system";
  } catch {
    return "system";
  }
}

export function useColorScheme(): [ColorScheme, (s: ColorScheme) => void] {
  const [scheme, setScheme] = useState<ColorScheme>(readColorScheme);
  useEffect(() => {
    applyColorScheme(scheme);
    if (scheme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyColorScheme("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [scheme]);
  const update = useCallback((s: ColorScheme) => {
    try {
      localStorage.setItem(STORAGE_KEY, s);
    } catch {
      /* private mode: preference lasts for this page only */
    }
    setScheme(s);
  }, []);
  return [scheme, update];
}

/** A device-local UI preference (e.g. the student portal's language). The one sanctioned place for
 * localStorage writes, besides the colour scheme: never session data or anything personal. */
export function readUiPref(key: string): string | null {
  try {
    return localStorage.getItem(`sc.${key}`);
  } catch {
    return null;
  }
}

export function writeUiPref(key: string, value: string): void {
  try {
    localStorage.setItem(`sc.${key}`, value);
  } catch {
    /* private mode: the preference lasts for this page only */
  }
}
