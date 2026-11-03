// Exporting and importing all data, in Settings. The server checks a file before anything
// changes and keeps a safety copy, so an import can be undone.
import { shortDate, plural } from "./format.js";
import { whenSettingsOpen } from "./settings.js";
import { $, api, confirmDialog, toast } from "./ui.js";

const describe = (s) => {
  const period = s.first_date ? `, from ${shortDate(s.first_date)} ${s.first_date.slice(0, 4)} to ${shortDate(s.last_date)} ${s.last_date.slice(0, 4)}` : "";
  return `${plural(s.transactions, "transaction")}${period}`;
};

async function refreshUndo() {
  const { can_undo: canUndo, last } = await api("/api/backup-status");
  $("#undo-import").hidden = !canUndo;
  $("#undo-import").textContent = last === "delete" ? "Undo deleting your data" : "Undo last import";
}
whenSettingsOpen(refreshUndo);

// Everything on the page changes, so finish by reloading it.
async function done(title, message) {
  await confirmDialog({ title, message, cancel: null });
  location.reload();
}

$("#export-btn").onclick = () => toast("This file holds all your financial data, so keep it somewhere safe");

$("#import-btn").onclick = () => $("#import-file").click();
$("#import-file").onchange = async (e) => {
  const file = e.target.files[0];
  e.target.value = ""; // so the same file can be chosen again
  if (!file) return;
  const data = await file.arrayBuffer();
  const { backup, current } = await api("/api/backup-check", { method: "POST", body: data });
  const ok = await confirmDialog({
    title: "Replace your data with this backup?",
    message: `The backup has ${describe(backup)}. It replaces everything now in Budget (${describe(current)}), including your settings. A safety copy is kept, so you can undo this.`,
    confirm: "Replace my data", danger: true,
  });
  if (!ok) return;
  const imported = await api("/api/backup-restore", { method: "POST", body: data });
  await done("Your data is imported", `Budget now has ${describe(imported)}. Changed your mind? Choose Undo last import in Settings.`);
};

$("#undo-import").onclick = async () => {
  const ok = await confirmDialog({
    title: "Undo the last import?",
    message: "This brings back your data from just before the import. Anything you added since then is lost.",
    confirm: "Undo import", danger: true,
  });
  if (!ok) return;
  const restored = await api("/api/backup-undo", { method: "POST" });
  await done("Import undone", `Budget now has ${describe(restored)}.`);
};

// Deleting all data: only after an export, or after saying explicitly that no copy is needed.
const clearReady = () => ($("#clear-confirm").disabled = $("#clear-exported").hidden && !$("#clear-skip").checked);
$("#clear-btn").onclick = () => {
  $("#clear-exported").hidden = true;
  $("#clear-skip").checked = false;
  clearReady();
  $("#clear-dialog").showModal();
};
$("#clear-export").onclick = () => {
  $("#clear-exported").hidden = false;
  clearReady();
};
$("#clear-skip").onchange = clearReady;
$("#clear-confirm").onclick = async () => {
  await api("/api/clear-data", { method: "POST", body: { confirm: true } });
  $("#clear-dialog").close();
  await done("Your data is deleted", "Budget is empty now. Changed your mind? Choose Undo in Settings to bring it all back.");
};
