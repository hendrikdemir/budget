// Backups in Settings: creating one, restoring one, and deleting all data. Before a restore
// or a delete, the user creates a backup of the current data first, or says no copy is needed.
import { shortDate, plural } from "./format.js";
import { $, api, confirmDialog, toast } from "./ui.js";

const describe = (s) => {
  const period = s.first_date ? `, from ${shortDate(s.first_date)} ${s.first_date.slice(0, 4)} to ${shortDate(s.last_date)} ${s.last_date.slice(0, 4)}` : "";
  return `${plural(s.transactions, "transaction")}${period}`;
};

// Everything on the page changes, so finish by reloading it.
async function done(title, message) {
  await confirmDialog({ title, message, cancel: null });
  location.reload();
}

// Asks to go ahead with replacing or deleting all data. Resolves true once the user created a
// backup or ticked that they don't need one, and then confirmed; false when cancelled.
function carefully({ title, text, skip, confirm }) {
  const dialog = $("#careful-dialog");
  $("#careful-title").textContent = title;
  $("#careful-text").textContent = text;
  $("#careful-skip-text").textContent = skip;
  $("#careful-confirm").textContent = confirm;
  $("#careful-done").hidden = true;
  $("#careful-skip").checked = false;
  const ready = () => ($("#careful-confirm").disabled = $("#careful-done").hidden && !$("#careful-skip").checked);
  ready();
  $("#careful-backup").onclick = () => { $("#careful-done").hidden = false; ready(); };
  $("#careful-skip").onchange = ready;
  dialog.showModal();
  return new Promise((resolve) => {
    $("#careful-confirm").onclick = () => { dialog.close(); resolve(true); };
    dialog.onclose = () => resolve(false); // resolving twice does nothing
  });
}

$("#export-btn").onclick = () => toast("Keep your backup somewhere safe: it holds all your financial data.", 4);

$("#import-btn").onclick = () => $("#import-file").click();
$("#import-file").onchange = async (e) => {
  const file = e.target.files[0];
  e.target.value = ""; // so the same file can be chosen again
  if (!file) return;
  const data = await file.arrayBuffer();
  const { backup, current } = await api("/api/backup-check", { method: "POST", body: data });
  const ok = await carefully({
    title: "Replace your data with this backup?",
    text: `The backup has ${describe(backup)}. It replaces everything now in Budget (${describe(current)}), including your budgets and settings. To add transactions from your bank instead, use Import above your transactions.`,
    skip: "Replace without a backup. I don't need a copy of my current data.",
    confirm: "Replace my data",
  });
  if (!ok) return;
  const restored = await api("/api/backup-restore", { method: "POST", body: data });
  await done("Your backup is restored", `Budget now has ${describe(restored)}.`);
};

$("#clear-btn").onclick = async () => {
  const ok = await carefully({
    title: "Delete all your data?",
    text: "This deletes all your transactions, budgets, account balances, and the income and costs you planned in the Outlook. Budget's automatic backups are deleted too, so this can't be undone. Your theme and currency stay.",
    skip: "Delete without a backup. I don't need a copy.",
    confirm: "Delete all data",
  });
  if (!ok) return;
  await api("/api/clear-data", { method: "POST", body: { confirm: true } });
  await done("Your data is deleted", "Budget is empty now. If you created a backup, you can bring it back with Restore from backup in Settings.");
};
