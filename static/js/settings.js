// Appearance: light/dark theme and currency, stored on the server.
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
  document.querySelectorAll("#currency-options button").forEach((b) => b.classList.toggle("active", b.dataset.currency === settings.currency));
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
$("#currency-options").onclick = (e) => e.target.dataset.currency && update({ currency: e.target.dataset.currency });
$("#settings-btn").onclick = () => {
  $("#settings").showModal();
  onOpen();
};
matchMedia("(prefers-color-scheme: dark)").onchange = applySettings;
