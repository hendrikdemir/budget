// Starts the page: settings and the current page (overview, #history or #outlook).
import "./bank-import.js";
import "./data.js";
import { renderHistory } from "./history.js";
import { renderOutlook } from "./outlook.js";
import { load } from "./overview.js";
import { currentMonth, today } from "./format.js";
import { state } from "./state.js";
import { loadSettings } from "./settings.js";
import { openTransaction } from "./transaction.js";
import { $ } from "./ui.js";
import { checkForUpdate } from "./updates.js";

function showPage() {
  const page = { "#outlook": "outlook", "#history": "history" }[location.hash] || "overview";
  for (const view of ["overview", "history", "outlook"]) $(`#${view}-view`).hidden = page !== view;
  document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("active", a.dataset.view === page));
  if (page === "outlook") renderOutlook();
  if (page === "history") renderHistory();
}
addEventListener("hashchange", showPage);

$("#add-btn").onclick = () => openTransaction();
$("#income-btn").onclick = () => openTransaction(null, "income");

await loadSettings(() => {
  load();
  if (location.hash === "#outlook") renderOutlook();
  if (location.hash === "#history") renderHistory();
});
showPage();
load();
checkForUpdate();

// A new day while the app stayed open (say, the lid was closed overnight): "Today", the
// current month and the expected balances are out of date, so load everything again. A
// page that was on the month that just ended moves on to the new one. Checked when the
// window comes back and every minute (timers run again after the Mac wakes up). Not while
// a dialog is open, so nothing being filled in changes; the next check catches up.
let day = today(), month = currentMonth();
function catchUpWithToday() {
  if (today() === day || document.querySelector("dialog[open]")) return;
  if (state.month === month) state.month = currentMonth();
  day = today();
  month = currentMonth();
  load();
}
document.addEventListener("visibilitychange", () => document.hidden || catchUpWithToday());
addEventListener("focus", catchUpWithToday);
setInterval(catchUpWithToday, 60 * 1000);
