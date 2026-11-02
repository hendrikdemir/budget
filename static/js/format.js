// Formatting and parsing. Money is whole cents everywhere; it's only turned into euros
// (or the chosen currency) for display, and parsed back into cents from user input.
import { state } from "./state.js";

export const pad = (n) => String(n).padStart(2, "0");
export const isoDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const today = () => isoDate(new Date());

export function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
}
export function shiftMonth(ym, delta) {
  const [y, m] = ym.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
}
// Last day of a "YYYY-MM" month.
export function monthEnd(ym) {
  const [y, m] = ym.split("-").map(Number);
  return isoDate(new Date(y, m, 0));
}

// Month and day names are English, like the rest of the interface; numbers and amounts
// follow the browser's language (e.g. "1.234,56" in Dutch).
export const DATE_LOCALE = "en-GB";
export const capitalize = (text) => text.replace(/^./, (c) => c.toUpperCase());
export function monthName(ym, style = "long") {
  const [y, m] = ym.split("-").map(Number);
  return capitalize(new Date(y, m - 1).toLocaleDateString(DATE_LOCALE, { month: style, year: "numeric" }));
}
// Just the month: "October" (long) or "Oct" (short).
export function monthOnly(ym, style = "short") {
  const [y, m] = ym.split("-").map(Number);
  return capitalize(new Date(y, m - 1).toLocaleDateString(DATE_LOCALE, { month: style }));
}
// "29 Oct" style dates.
export const shortDate = (iso) => new Intl.DateTimeFormat(DATE_LOCALE, { day: "numeric", month: "short" })
  .formatToParts(new Date(iso + "T00:00")).map((p) => (p.type === "month" ? capitalize(p.value) : p.value)).join("");

// Cents as money, e.g. 123456 -> "€ 1.234,56".
export function money(cents, { whole = false } = {}) {
  return new Intl.NumberFormat(undefined, {
    style: "currency", currency: state.settings.currency, ...(whole ? { maximumFractionDigits: 0 } : {}),
  }).format(cents / 100);
}
export const currencySymbol = () => (0).toLocaleString(undefined, { style: "currency", currency: state.settings.currency }).replace(/[\d.,\s]/g, "");

// User input to cents. Accepts "12.50", "12,50", "1.234,50", "-250" and "21," (while
// typing). Returns NaN for anything else.
export function parseAmount(text) {
  let t = String(text).trim().replace(/\s|€|\$|£/g, "");
  if (t.includes(",") && t.includes(".")) t = t.replace(/\./g, "");
  t = t.replace(",", ".");
  return /^-?\d+(\.\d{0,2})?$/.test(t) ? Math.round(Number(t) * 100) : NaN;
}
// Cents for an input field, in the style shown elsewhere: 123456 -> "1234,56".
export const inputAmount = (cents) => (cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false });

export function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
export const plural = (n, word) => `${n} ${n === 1 ? word : `${word}s`}`;
