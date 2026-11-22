// Backups in Settings: creating one, restoring one, and deleting all data. Before a restore
// or a delete, the user creates a backup of the current data first, or says no copy is needed.
import { DATE_LOCALE, cap, shortDate } from "./format.js";
import { html, setHtml } from "./html.js";
import { t } from "./i18n.js";
import { $, api, confirmDialog, toast } from "./ui.js";

const describe = (s) => {
  const transactions = t("common.transactionCount", { count: s.transactions });
  return s.first_date ? t("backup.fromTo", {
    transactions, first: `${shortDate(s.first_date)} ${s.first_date.slice(0, 4)}`, last: `${shortDate(s.last_date)} ${s.last_date.slice(0, 4)}`,
  }) : transactions;
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

$("#export-btn").onclick = () => toast(t("backup.keepYourBackupSomewhereSafe"), 4);

// Restoring: a backup file you created, or one of the automatic backups.
const longDate = (iso) => cap(new Date(`${iso}T00:00`).toLocaleDateString(DATE_LOCALE, { weekday: "short", day: "numeric", month: "long", year: "numeric" }));
$("#import-btn").onclick = async () => {
  const copies = await api("/api/auto-backups");
  setHtml($("#auto-backups"), copies.length
    ? html`${copies.map((c) => html`<li><button type="button" class="auto-backup" data-name="${c.name}">
        <span>${longDate(c.date)}</span><span class="muted">${t("common.transactionCount", { count: c.transactions })}</span></button></li>`)}`
    : html`<li class="muted">${t("backup.noAutomaticBackupsYet")}</li>`);
  $("#restore-dialog").showModal();
};
$("#restore-file").onclick = () => $("#import-file").click();

async function restore(check, run, what) {
  const { backup, current } = await check();
  const ok = await carefully({
    title: t("backup.replaceYourDataWithThis"),
    text: t("backup.hasItReplacesEverythingNow",
      { what, backup: describe(backup), current: describe(current) }),
    skip: t("backup.replaceWithoutABackupI"),
    confirm: t("backup.replaceMyData"),
  });
  if (!ok) return;
  const restored = await run();
  $("#restore-dialog").close();
  await done(t("backup.yourBackupIsRestored"), t("backup.budgetNowHas", { what: describe(restored) }));
}
$("#import-file").onchange = async (e) => {
  const file = e.target.files[0];
  e.target.value = ""; // so the same file can be chosen again
  if (!file) return;
  const data = await file.arrayBuffer();
  await restore(() => api("/api/backup-check", { method: "POST", body: data }),
    () => api("/api/backup-restore", { method: "POST", body: data }), t("backup.theBackup"));
};
$("#auto-backups").onclick = async (e) => {
  const button = e.target.closest(".auto-backup");
  if (!button) return;
  const name = button.dataset.name;
  await restore(() => api("/api/auto-backup-check", { method: "POST", body: { name } }),
    () => api("/api/auto-backup-restore", { method: "POST", body: { name } }),
    t("backup.theAutomaticBackupOf", { date: button.querySelector("span").textContent }));
};

$("#clear-btn").onclick = async () => {
  const ok = await carefully({
    title: t("backup.deleteAllYourData"),
    text: t("backup.thisDeletesAllYourTransactions"),
    skip: t("backup.deleteWithoutABackupI"),
    confirm: t("backup.deleteAllData"),
  });
  if (!ok) return;
  await api("/api/clear-data", { method: "POST", body: { confirm: true } });
  await done(t("backup.yourDataIsDeleted"), t("backup.budgetIsEmptyNowIf"));
};
