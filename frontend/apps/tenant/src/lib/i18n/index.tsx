/**
 * Languages for the student and parent screens (decision D29): English, Hindi and Punjabi.
 *
 * A small catalogue rather than an i18n library, so the student bundle stays under its budget (P10.5):
 * English is built in; Hindi and Punjabi are separate chunks, loaded only when chosen. The language is the
 * one picked on this device, else the institution's default (settings → language), else English. Outside
 * the provider (staff screens, where administrators preview a result) everything is English.
 *
 * Adding a language: a catalogue next to en.ts (the compiler checks every key), an entry in LANGUAGES and
 * LOADERS, and its column in backend/app/modules/documents/labels.py for the marksheet.
 */
import { readUiPref, writeUiPref } from "@scorecode/ui";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import en, { type Catalogue, type MessageKey } from "./en";

export type Lang = "en" | "hi" | "pa";
export type { MessageKey };

export const LANGUAGES: readonly { code: Lang; name: string }[] = [
  { code: "en", name: "English" },
  { code: "hi", name: "हिन्दी" },
  { code: "pa", name: "ਪੰਜਾਬੀ" },
];
const LOADERS: Record<Exclude<Lang, "en">, () => Promise<{ default: Catalogue }>> = {
  hi: () => import("./hi"),
  pa: () => import("./pa"),
};
const PREF = "lang"; // stored as sc.lang

const isLang = (v: unknown): v is Lang => v === "en" || v === "hi" || v === "pa";

/** `hi-IN` → `hi`; anything unknown → `en`. */
export function langOf(locale: string | null | undefined): Lang {
  const l = (locale ?? "en").split("-")[0]?.toLowerCase();
  return isLang(l) ? l : "en";
}

function stored(): Lang | null {
  const v = readUiPref(PREF); // null in private windows: the institution's default then
  return isLang(v) ? v : null;
}

type Vars = Record<string, string | number>;
type CountKey<K> = K extends `${infer B}_one` ? B : never;

export interface I18n {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: MessageKey, vars?: Vars) => string;
  /** A count: picks `key_one` or `key_other` and fills `{n}`. */
  tn: (key: CountKey<MessageKey>, n: number, vars?: Vars) => string;
  dateTime: (iso: string | null | undefined) => string;
  date: (iso: string | null | undefined) => string;
  relative: (iso: string | null | undefined) => string;
}

function fill(text: string, vars?: Vars): string {
  return vars ? text.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m)) : text;
}

function build(lang: Lang, cat: Catalogue, setLang: (l: Lang) => void): I18n {
  const tag = `${lang}-IN`;
  // Western digits in every language, as Indian result documents use.
  const dt = new Intl.DateTimeFormat(tag, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    numberingSystem: "latn",
  });
  const d = new Intl.DateTimeFormat(tag, {
    day: "numeric",
    month: "short",
    year: "numeric",
    numberingSystem: "latn",
  });
  const rtf = new Intl.RelativeTimeFormat(tag, {
    numeric: "auto",
    numberingSystem: "latn",
  } as Intl.RelativeTimeFormatOptions);
  const t = (key: MessageKey, vars?: Vars) => fill(cat[key] ?? en[key], vars);
  return {
    lang,
    setLang,
    t,
    tn: (key, n, vars) => t(`${key}_${n === 1 ? "one" : "other"}` as MessageKey, { n, ...vars }),
    dateTime: (iso) => (iso ? dt.format(new Date(iso)) : "—"),
    date: (iso) => (iso ? d.format(new Date(iso)) : "—"),
    relative: (iso) => {
      if (!iso) return "—";
      const s = Math.round((new Date(iso).getTime() - Date.now()) / 1000);
      const a = Math.abs(s);
      if (a < 45) return rtf.format(0, "second");
      if (a < 3600) return rtf.format(Math.round(s / 60), "minute");
      if (a < 86400) return rtf.format(Math.round(s / 3600), "hour");
      if (a < 86400 * 30) return rtf.format(Math.round(s / 86400), "day");
      return d.format(new Date(iso));
    },
  };
}

const ENGLISH = build("en", en, () => {});
const Ctx = createContext<I18n | null>(null);

export function I18nProvider({
  defaultLocale,
  children,
}: {
  defaultLocale?: string | null;
  children: ReactNode;
}) {
  const [lang, setLangState] = useState<Lang>(() => stored() ?? langOf(defaultLocale));
  // The catalogue loaded last, with its language: until the chosen one arrives, English (never another).
  const [loaded, setLoaded] = useState<{ lang: Lang; cat: Catalogue }>({ lang: "en", cat: en });
  useEffect(() => {
    let live = true;
    if (lang !== "en")
      LOADERS[lang]()
        .then((m) => live && setLoaded({ lang, cat: m.default }))
        .catch(() => undefined); // offline mid-switch: stay readable in English
    const root = document.documentElement;
    const before = root.lang;
    root.lang = lang;
    return () => {
      live = false;
      root.lang = before;
    };
  }, [lang]);
  const cat = loaded.lang === lang ? loaded.cat : en;
  const value = useMemo(
    () =>
      build(lang, cat, (l) => {
        setLangState(l);
        writeUiPref(PREF, l);
      }),
    [lang, cat],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  return useContext(Ctx) ?? ENGLISH;
}
