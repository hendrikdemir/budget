// Appearance: light/dark theme and currency, stored on the server.
import { combobox } from "./controls.js";
import { state } from "./state.js";
import { $, api } from "./ui.js";

let onCurrencyChange = () => {};
let onOpen = () => {};
export const whenSettingsOpen = (action) => (onOpen = action);

export function applySettings() {
  const { settings } = state;
  const root = document.documentElement;
  const dark = settings.theme === "dark" || (settings.theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  root.dataset.theme = dark ? "dark" : "light";
  document.querySelectorAll("#theme-options button").forEach((b) => b.classList.toggle("active", b.dataset.theme === settings.theme));
  currencyPicker.set(settings.currency);
}

export async function loadSettings(currencyChanged) {
  onCurrencyChange = currencyChanged;
  const [settings, { version }] = await Promise.all([api("/api/settings"), api("/api/version")]);
  state.settings = settings;
  $("#app-version").textContent = `Budget ${version}`;
  applySettings();
}

function update(patch) {
  Object.assign(state.settings, patch);
  applySettings();
  api("/api/settings", { method: "POST", body: patch });
  if ("currency" in patch) onCurrencyChange();
}

$("#theme-options").onclick = (e) => e.target.dataset.theme && update({ theme: e.target.dataset.theme });
// Every currency the browser knows, searchable by code or English name.
const currencyName = new Intl.DisplayNames(["en"], { type: "currency" });
const CURRENCIES = (Intl.supportedValuesOf?.("currency") ?? ["EUR", "USD", "GBP", "CHF"])
  .map((code) => ({ value: code, name: currencyName.of(code) }))
  .filter((c) => c.name && c.name !== c.value)
  .map((c) => ({ value: c.value, label: `${c.value} · ${c.name}` }));
const currencyPicker = combobox($("#currency-input"), {
  options: () => CURRENCIES,
  strict: true,
  onSelect: (o) => o.value !== state.settings.currency && update({ currency: o.value }),
});
// Typing replaces the current choice; leaving the field without choosing keeps it.
$("#currency-input").addEventListener("focus", (e) => setTimeout(() => e.target.select()));
$("#currency-input").addEventListener("blur", () => currencyPicker.value || currencyPicker.set(state.settings.currency));
$("#settings-btn").onclick = () => {
  $("#settings").showModal();
  onOpen();
};
matchMedia("(prefers-color-scheme: dark)").onchange = applySettings;
