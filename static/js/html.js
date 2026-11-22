// HTML that escapes by default. The page builds its HTML from templates, and much of what goes
// in comes from the user or a bank export (payees, notes, budget names). Written with html`…`,
// every value is escaped unless it's HTML made the same way, so a payee called
// "<img onerror=…>" shows as text. Lists of html`…` can go in as they are.
//
//   setHtml(el, html`<b>${name}</b> ${rows.map((r) => html`<li>${r}</li>`)}`);
//
// Only setHtml() puts HTML into the page, and it takes nothing but html`…` (or th() from i18n.js,
// a translation whose own markup is trusted and whose values are escaped).

export class Html {
  constructor(text) {
    this.text = text;
  }
  toString() {
    return this.text;
  }
}

/** @param {unknown} text */
export function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c);
}

/** A value in a template: HTML as it is, a list piece by piece, nothing for null/undefined/false. */
function piece(value) {
  if (value instanceof Html) return value.text;
  if (Array.isArray(value)) return value.map(piece).join("");
  if (value === null || value === undefined || value === false) return "";
  return escapeHtml(value);
}

/**
 * @param {TemplateStringsArray} strings
 * @param {...unknown} values
 */
export function html(strings, ...values) {
  return new Html(strings.reduce((out, text, i) => out + text + (i < values.length ? piece(values[i]) : ""), ""));
}

/**
 * Pieces with a separator between them, like Array.join, keeping each piece escaped.
 * @param {unknown[]} pieces
 * @param {string} separator
 */
export const join = (pieces, separator) => html`${pieces.map((p, i) => (i ? html`${separator}${p}` : html`${p}`))}`;

/** Markup that is part of the app itself (an icon, say): never anything from the user. */
export const trusted = (/** @type {string} */ text) => new Html(text);

/**
 * The first element of html`…`, to put somewhere in the page (say, with replaceWith).
 * @param {Html} content
 */
export function element(content) {
  const template = document.createElement("template");
  setHtml(template, content);
  return /** @type {Element} */ (template.content.firstElementChild);
}

/**
 * @param {Element} el
 * @param {Html} content
 */
export function setHtml(el, content) {
  if (!(content instanceof Html)) throw new TypeError("setHtml takes html`…`, so everything in it is escaped");
  el.innerHTML = content.text;
}
