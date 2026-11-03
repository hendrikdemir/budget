// Backups in Settings: creating one, restoring one, and deleting all data. Before a restore
// or a delete, the user creates a backup of the current data first, or says no copy is needed.
import { DATE_LOCALE, escapeHtml, plural, shortDate } from "./format.js";
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

// Restoring: a backup file you created, or one of the automatic backups.
const longDate = (iso) => new Date(`${iso}T00:00`).toLocaleDateString(DATE_LOCALE, { weekday: "short", day: "numeric", month: "long", year: "numeric" });
$("#import-btn").onclick = async () => {
  const copies = await api("/api/auto-backups");
  $("#auto-backups").innerHTML = copies.length
    ? copies.map((c) => `<li><button type="button" class="auto-backup" data-name="${escapeHtml(c.name)}">
        <span>${longDate(c.date)}</span><span class="muted">${plural(c.transactions, "transaction")}</span></button></li>`).join("")
    : `<li class="muted">No automatic backups yet.</li>`;
  $("#restore-dialog").showModal();
};
$("#restore-file").onclick = () => $("#import-file").click();

async function restore(check, run, what) {
  const { backup, current } = await check();
  const ok = await carefully({
    title: "Replace your data with this backup?",
    text: `${what} has ${describe(backup)}. It replaces everything now in Budget (${describe(current)}), including your budgets and settings. To add transactions from your bank instead, use Import above your transactions.`,
    skip: "Replace without a backup. I don't need a copy of my current data.",
    confirm: "Replace my data",
  });
  if (!ok) return;
  const restored = await run();
  $("#restore-dialog").close();
  await done("Your backup is restored", `Budget now has ${describe(restored)}.`);
}
$("#import-file").onchange = async (e) => {
  const file = e.target.files[0];
  e.target.value = ""; // so the same file can be chosen again
  if (!file) return;
  const data = await file.arrayBuffer();
  await restore(() => api("/api/backup-check", { method: "POST", body: data }),
    () => api("/api/backup-restore", { method: "POST", body: data }), "The backup");
};
$("#auto-backups").onclick = async (e) => {
  const button = e.target.closest(".auto-backup");
  if (!button) return;
  const name = button.dataset.name;
  await restore(() => api("/api/auto-backup-check", { method: "POST", body: { name } }),
    () => api("/api/auto-backup-restore", { method: "POST", body: { name } }),
    `The automatic backup of ${button.querySelector("span").textContent}`);
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
