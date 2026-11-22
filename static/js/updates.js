// "A new version is available": a banner, a dialog with what's new and how to install it,
// and the Updates choice in Settings. The server checks GitHub (app/updates.py); the page only shows it.
import { t } from "./i18n.js";
import { state } from "./state.js";
import { $, api } from "./ui.js";

let release = { available: false };
let hiddenForNow = false; // the banner's ×: hidden until Budget restarts

function render() {
  const checking = state.settings.update_check !== "off";
  $("#update-check").checked = checking;
  $("#update-banner").hidden = !release.available || release.skipped || hiddenForNow;
  $("#update-banner-text").textContent = t("updates.budgetIsAvailable", { version: release.version });
  const hint = $("#update-hint");
  hint.textContent = !checking ? t("updates.budgetWontLookForNew")
    : release.available ? t("updates.budgetIsAvailable", { version: release.version })
    : release.checked ? t("updates.youHaveTheLatestVersion")
    : t("updates.budgetCouldntCheckForA");
  if (checking && release.available) {
    const link = hint.appendChild(Object.assign(document.createElement("button"), { type: "button", className: "link-btn", textContent: t("updates.howToUpdate") }));
    link.style.marginLeft = "6px";
    link.onclick = openUpdate;
  }
}

function openUpdate() {
  $("#update-title").textContent = t("updates.updateToBudget", { version: release.version });
  $("#update-current").textContent = t("updates.youHaveBudget", { version: release.current });
  $("#update-notes").textContent = release.notes; // plain text, never HTML from the internet
  $("#update-notes-block").hidden = !release.notes;
  $("#update-download").href = release.download;
  const platform = release.platform === "windows" ? "windows" : "mac";
  document.querySelectorAll(".update-steps").forEach((steps) => (steps.hidden = steps.dataset.platform !== platform));
  $("#update-skip").hidden = release.skipped;
  $("#settings").open && $("#settings").close();
  $("#update-dialog").showModal();
}

async function saveSetting(patch) {
  Object.assign(state.settings, patch);
  await api("/api/settings", { method: "POST", body: patch });
}

export async function checkForUpdate() {
  try {
    release = await fetch("/api/update").then((r) => (r.ok ? r.json() : { available: false }));
  } catch {
    release = { available: false }; // no update shown is fine; never bother the user about this
  }
  render();
}

$("#update-how").onclick = openUpdate;
$("#update-later").onclick = () => { hiddenForNow = true; render(); };
$("#update-download").onclick = () => setTimeout(() => $("#update-dialog").close());
$("#update-skip").onclick = async () => {
  $("#update-dialog").close();
  release.skipped = true;
  render();
  await saveSetting({ skipped_version: release.version });
};
$("#update-check").onchange = async (e) => {
  const check = e.target.checked ? "on" : "off";
  await saveSetting({ update_check: check });
  if (check === "on") await checkForUpdate();
  else { release = { available: false }; render(); }
};
