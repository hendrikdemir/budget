// Languages. Every text of the page is in static/lang/<code>.json under a named key, grouped by
// the part of the app it's in: en.json is the source, other languages translate the same keys.
// The files use i18next's JSON format (v4), which translation tools read:
//
//   "budgets": { "editBudgets": "Edit budgets", "addedCount_one": "Added {{count}} budget", "addedCount_other": "…" }
//
// t("budgets.editBudgets") gives the text; t("budgets.addedCount", { count: 3 }) fills in {{count}} and
// picks the plural form this language uses for 3 (Intl.PluralRules: one, few, many, other, …).
// Values are inserted as they are: escape anything typed by the user before passing it.
// A key a language doesn't have yet falls back to English. The static page names its keys:
// data-i18n (text), data-i18n-html (HTML), data-i18n-placeholder, data-i18n-aria-label and
// data-i18n-title. The server reads the same files for its messages (app/i18n.py).
//
// In HTML, use th(): it gives html`…` (html.js), with the translation's own markup kept and the
// values escaped, unless they're html`…` themselves.
//
// To add a language: add its file and an entry in LANGUAGES here and in app/i18n.py.
// tests/test_i18n.py checks that every key the code uses exists, in every language.

export const LANGUAGES = {
  en: { name: "English", locale: "en-GB" },
  nl: { name: "Nederlands", locale: "nl-NL" },
};

// "system": the computer's language when Budget has it, else English.
export function resolveLanguage(setting) {
  if (LANGUAGES[setting]) return setting;
  const preferred = (navigator.languages || [navigator.language]).map((l) => String(l).slice(0, 2).toLowerCase());
  return preferred.find((l) => LANGUAGES[l]) || "en";
}

const load = async (code) => {
  try {
    return await (await fetch(`lang/${code}.json`)).json();
  } catch {
    return {};
  }
};
const lookup = (strings, key) => key.split(".").reduce((node, part) => (node && typeof node === "object" ? node[part] : undefined), strings);

// The language is chosen in Settings; start with it, so every text is right from the first render.
let setting = "system";
try {
  setting = (await (await fetch("/api/settings")).json()).language || "system";
} catch {}
export const language = resolveLanguage(setting);
export const locale = LANGUAGES[language].locale;
const english = await load("en");
const strings = language === "en" ? english : await load(language);
const plurals = new Intl.PluralRules(locale);

import { Html, escapeHtml } from "./html.js";

/**
 * @param {string} key
 * @param {Record<string, unknown>} [params]
 */
export function t(key, params = {}) {
  return fill(translation(key, params), params, String);
}

/**
 * The translation as HTML: its own markup (from the language file) kept, the values escaped.
 * @param {string} key
 * @param {Record<string, unknown>} [params]
 */
export const th = (key, params = {}) =>
  new Html(fill(escapeHtml(translation(key, params)).replace(MARKUP, (m, tag) => `<${tag.replaceAll("&quot;", '"')}>`), params,
    (value) => (value instanceof Html ? value.text : escapeHtml(value))));

// The only markup a translation may have: bold text, with an id for the page to fill in.
const MARKUP = /&lt;(\/?(?:b|strong)(?: id=&quot;[\w-]+&quot;)?)&gt;/g;
const fill = (text, params, show) => text.replace(/\{\{\s*(\w+)\s*\}\}/g, (m, name) => (name in params ? show(params[name]) : m));

function translation(key, params) {
  const keys = "count" in params ? [`${key}_${plurals.select(params.count)}`, `${key}_other`, key] : [key];
  let text;
  for (const source of [strings, english]) {
    text = keys.map((k) => lookup(source, k)).find((v) => typeof v === "string");
    if (text !== undefined) break;
  }
  return text ?? key;
}

const ATTRIBUTES = ["placeholder", "aria-label", "title"];
export function translatePage(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => (el.textContent = t(el.dataset.i18n)));
  root.querySelectorAll("[data-i18n-html]").forEach((el) => (el.innerHTML = th(el.dataset.i18nHtml).text));
  for (const attribute of ATTRIBUTES) {
    root.querySelectorAll(`[data-i18n-${attribute}]`).forEach((el) => el.setAttribute(attribute, t(el.getAttribute(`data-i18n-${attribute}`))));
  }
}

document.documentElement.lang = language;
translatePage();
