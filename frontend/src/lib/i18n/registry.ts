/**
 * Locale registry — the single place that knows which languages exist.
 *
 * Adding a language is a three-line change and nothing else:
 *   1. drop the generated dictionary at `src/lib/i18n/locales/<tag>.ts`
 *      (`node scripts/build-locale.mjs <tag>`, see scripts/locales/<tag>.json)
 *   2. add one LOCALES entry below with a lazy `load()`
 *   3. done — the store, the overlay and the sidebar switch all read this list.
 *
 * `en` is the *source* language: the app renders English, so it carries no
 * dictionary and is the only locale without a `load()`. Dictionaries are
 * imported on demand so the bundle carries the English base plus the one
 * language the user actually picked, not all six.
 */

export type LocaleDictionary = {
  /** Exact English text node → translated text. */
  phrases: Record<string, string>;
  /** Values of `phrases`, so a node already in the target language is never re-translated. */
  translated: Set<string>;
};

export type LocaleDescriptor = {
  /** Stored in localStorage and written to `<html lang>`. */
  tag: string;
  /** The language written in its own script — what a picker should show. */
  nativeName: string;
  /** English name, for mixed-language lists and screen readers. */
  englishName: string;
  /** Compact label for tight slots (a 1-2 char tag). Unused by the Settings
   *  picker, which always has room for `nativeName` — kept for a switch that
   *  lives somewhere narrow, e.g. a re-added collapsed-sidebar control. */
  shortName: string;
  dir: "ltr" | "rtl";
  /** Omitted for the source language. */
  load?: () => Promise<LocaleDictionary>;
};

export const BASE_LOCALE = "en";

const lazy = (
  importer: () => Promise<{ default: LocaleDictionary }>,
): (() => Promise<LocaleDictionary>) => () => importer().then((m) => m.default);

export const LOCALES: LocaleDescriptor[] = [
  { tag: "en", nativeName: "English", englishName: "English", shortName: "EN", dir: "ltr" },
  {
    tag: "zh-CN",
    nativeName: "简体中文",
    englishName: "Chinese (Simplified)",
    shortName: "简",
    dir: "ltr",
    load: lazy(() => import("./locales/zh-CN")),
  },
  {
    tag: "zh-TW",
    nativeName: "繁體中文",
    englishName: "Chinese (Traditional)",
    shortName: "繁",
    dir: "ltr",
    load: lazy(() => import("./locales/zh-TW")),
  },
  {
    tag: "ja",
    nativeName: "日本語",
    englishName: "Japanese",
    shortName: "日",
    dir: "ltr",
    load: lazy(() => import("./locales/ja")),
  },
  {
    tag: "ko",
    nativeName: "한국어",
    englishName: "Korean",
    shortName: "한",
    dir: "ltr",
    load: lazy(() => import("./locales/ko")),
  },
  {
    tag: "fr",
    nativeName: "Français",
    englishName: "French",
    shortName: "FR",
    dir: "ltr",
    load: lazy(() => import("./locales/fr")),
  },
];

/**
 * Tags stored by earlier builds, or reasonable spellings a user might arrive
 * with. Normalising here keeps the store and the switch honest about what is
 * actually installed.
 */
const ALIASES: Record<string, string> = {
  zh: "zh-CN",
  "zh-Hans": "zh-CN",
  "zh-Hant": "zh-TW",
  "zh-HK": "zh-TW",
  jp: "ja",
  "ja-JP": "ja",
  "ko-KR": "ko",
  "fr-FR": "fr",
  "en-US": "en",
};

const BY_TAG = new Map(LOCALES.map((l) => [l.tag, l]));

export function isSupported(tag: string): boolean {
  return BY_TAG.has(tag);
}

/** Any raw value (localStorage, URL, `null`) mapped onto an installed tag. */
export function normalizeTag(raw: string | null | undefined): string {
  if (!raw) return BASE_LOCALE;
  const exact = BY_TAG.has(raw) ? raw : ALIASES[raw];
  if (exact && BY_TAG.has(exact)) return exact;
  // "fr-CA" → "fr": accept regional variants of a language we do have.
  const base = raw.split(/[-_]/)[0].toLowerCase();
  const regionless = LOCALES.find((l) => l.tag.toLowerCase() === base);
  return regionless ? regionless.tag : BASE_LOCALE;
}

export function getDescriptor(tag: string): LocaleDescriptor {
  return BY_TAG.get(tag) ?? BY_TAG.get(BASE_LOCALE)!;
}

/** True for the source language, where the overlay has nothing to do. */
export function isSourceLanguage(tag: string): boolean {
  return !getDescriptor(tag).load;
}

/** Reflect the active locale on the document element (lang + dir). */
export function applyDocumentLocale(tag: string): void {
  const descriptor = getDescriptor(tag);
  try {
    document.documentElement.lang = descriptor.tag;
    document.documentElement.dir = descriptor.dir;
  } catch {
    /* not attached yet */
  }
}

const cache = new Map<string, LocaleDictionary>();

/** Already-resolved dictionary, or undefined while it is still on the wire. */
export function peekDictionary(tag: string): LocaleDictionary | undefined {
  return cache.get(tag);
}

/** Load and memoise a dictionary. The source language resolves to an empty one. */
export function loadDictionary(tag: string): Promise<LocaleDictionary> {
  const descriptor = getDescriptor(tag);
  const known = cache.get(descriptor.tag);
  if (known) return Promise.resolve(known);
  if (!descriptor.load) {
    const empty: LocaleDictionary = { phrases: {}, translated: new Set() };
    cache.set(descriptor.tag, empty);
    return Promise.resolve(empty);
  }
  return descriptor
    .load()
    .then((dictionary) => {
      cache.set(descriptor.tag, dictionary);
      return dictionary;
    })
    .catch(() => {
      // A failed chunk must not break the page — leave the English source visible.
      const empty: LocaleDictionary = { phrases: {}, translated: new Set() };
      cache.set(descriptor.tag, empty);
      return empty;
    });
}
