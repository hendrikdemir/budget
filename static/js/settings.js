// Settings stored on the server: language, how much Budget shows (the basics or every
// feature), light/dark theme, currency and how numbers are written.
import { combobox } from "./controls.js";
import { decimalComma, example } from "./format.js";
import { LANGUAGES, language, resolveLanguage, t } from "./i18n.js";
import { isSimple, state } from "./state.js";
import { $, api } from "./ui.js";

let onFormatChange = () => {}; // the currency, number format or features changed: the page shows things differently

export function applySettings() {
  const { settings } = state;
  const root = document.documentElement;
  const dark = settings.theme === "dark" || (settings.theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  root.dataset.theme = dark ? "dark" : "light";
  // Features beyond the basics have class full-only; style.css hides them in mode simple.
  root.dataset.mode = isSimple() ? "simple" : "full";
  document.querySelectorAll("#theme-options button").forEach((b) => b.classList.toggle("active", b.dataset.theme === settings.theme));
  document.querySelectorAll("#mode-options button").forEach((b) => b.classList.toggle("active", b.dataset.mode === (isSimple() ? "simple" : "full")));
  $("#mode-hint").textContent = isSimple()
    ? t("settings.yourBudgetsWhatYouSpend")
    : t("settings.alsoTheOutlookGettingReady");
  $("#language-select").value = settings.language;
  currencyPicker.set(settings.currency);
  // Without a choice, the way this computer writes numbers is the one in use.
  document.querySelectorAll("#number-options button").forEach((b) => b.classList.toggle("active", b.dataset.format === (decimalComma() ? "comma" : "point")));
  document.querySelectorAll(".money-input input").forEach((input) => (input.placeholder = example("0.00")));
}

export async function loadSettings(formatChanged) {
  onFormatChange = formatChanged;
  const [settings, { version }] = await Promise.all([api("/api/settings"), api("/api/version")]);
  state.settings = settings;
  $("#app-version").textContent = `Budget ${version}`;
  applySettings();
}

// Saves settings, and shows the page the way they say.
export async function updateSettings(patch) {
  Object.assign(state.settings, patch);
  applySettings();
  await api("/api/settings", { method: "POST", body: patch });
  if ("mode" in patch && isSimple() && location.hash === "#outlook") location.hash = "";
  if ("currency" in patch || "number_format" in patch || "mode" in patch) onFormatChange();
}
const update = (patch) => updateSettings(patch);

$("#theme-options").onclick = (e) => e.target.dataset.theme && update({ theme: e.target.dataset.theme });
$("#number-options").onclick = (e) => e.target.dataset.format && update({ number_format: e.target.dataset.format });
$("#mode-options").onclick = (e) => e.target.dataset.mode && e.target.dataset.mode !== state.settings.mode && update({ mode: e.target.dataset.mode });

// Languages: the system language, or one chosen. Each is named in its own language. Changing it
// reloads the page in the new language, with Settings open again.
$("#language-select").innerHTML = [
  `<option value="system">${t("settings.systemLanguage")} (${LANGUAGES[resolveLanguage("system")].name})</option>`,
  ...Object.entries(LANGUAGES).map(([code, l]) => `<option value="${code}">${l.name}</option>`),
].join("");
$("#language-select").onchange = async (e) => {
  await api("/api/settings", { method: "POST", body: { language: e.target.value } });
  try { sessionStorage.setItem("budget.open-settings", "1"); } catch {}
  location.reload();
};

// Every currency the browser knows, searchable by code or name.
const currencyName = new Intl.DisplayNames([language, "en"], { type: "currency" });
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
export function openSettings() {
  $("#settings").showModal();
}
$("#settings-btn").onclick = openSettings;
matchMedia("(prefers-color-scheme: dark)").onchange = applySettings;
