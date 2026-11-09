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

// Month and day names are English, like the rest of the interface. Numbers and amounts are
// written the way this Mac does, or as chosen in Settings: 1.234,56 or 1,234.56.
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

// How numbers are written. The setting number_format is "comma" (1.234,56), "point"
// (1,234.56) or "system": the way this Mac writes them.
const systemComma = (1.5).toLocaleString().includes(",");
export const decimalComma = () => state.settings.number_format === "comma" || (state.settings.number_format !== "point" && systemComma);
const separators = () => (decimalComma() ? { decimal: ",", group: "." } : { decimal: ".", group: "," });
// An example number in a message or placeholder, written the user's way: "12.50" -> "12,50".
export const example = (text) => text.replace(".", separators().decimal);

// Cents as money, e.g. 123456 -> "€ 1.234,56". A chosen number format only swaps the
// separators: where the currency symbol goes still follows this Mac.
export function money(cents, { whole = false } = {}) {
  const format = new Intl.NumberFormat(undefined, {
    style: "currency", currency: state.settings.currency, ...(whole ? { maximumFractionDigits: 0 } : {}),
  });
  if (!["comma", "point"].includes(state.settings.number_format)) return format.format(cents / 100);
  const { decimal, group } = separators();
  return format.formatToParts(cents / 100).map((p) => (p.type === "decimal" ? decimal : p.type === "group" ? group : p.value)).join("");
}
export const currencySymbol = () => (0).toLocaleString(undefined, { style: "currency", currency: state.settings.currency }).replace(/[\d.,\s]/g, "");

// User input to cents, read the way the user's numbers are written. With a decimal comma:
// "12,50", "1.234,50", "1.234", "-250" and "21," (while typing); with a decimal point the
// mirror image. The other separator before one or two digits can only be meant as the decimal
// one, so "12.50" is 12,50 either way. Returns NaN for anything else.
export function parseAmount(text) {
  const { decimal, group } = separators();
  const d = `\\${decimal}`, g = `\\${group}`;
  const t = String(text).trim().replace(/[\s\p{Sc}]/gu, "");
  const digits = t.replace(/^-/, "");
  let plain;
  if (new RegExp(`^\\d{1,3}(${g}\\d{3})+(${d}\\d{0,2})?$`).test(digits)) plain = digits.split(group).join("").replace(decimal, ".");
  else if (new RegExp(`^\\d+(${d}\\d{0,2})?$`).test(digits)) plain = digits.replace(decimal, ".");
  else if (new RegExp(`^\\d+${g}\\d{1,2}$`).test(digits)) plain = digits.replace(group, ".");
  else return NaN;
  return Math.round(Number(plain) * 100) * (t.startsWith("-") ? -1 : 1);
}
// Cents for an input field, in the style shown elsewhere: 123456 -> "1234,56".
export const inputAmount = (cents) => `${cents < 0 ? "-" : ""}${Math.floor(Math.abs(cents) / 100)}${separators().decimal}${pad(Math.abs(cents) % 100)}`;

export function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
export const plural = (n, word) => `${n} ${n === 1 ? word : `${word}s`}`;
