// Starts the page: settings, the current page (overview or #outlook) and keyboard shortcuts.
import "./bank-import.js";
import "./data.js";
import { renderOutlook } from "./outlook.js";
import { load } from "./overview.js";
import { loadSettings } from "./settings.js";
import { openTransaction } from "./transaction.js";
import { $ } from "./ui.js";

function showPage() {
  const page = location.hash === "#outlook" ? "outlook" : "overview";
  $("#overview-view").hidden = page !== "overview";
  $("#outlook-view").hidden = page !== "outlook";
  document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("active", a.dataset.view === page));
  if (page === "outlook") renderOutlook();
}
addEventListener("hashchange", showPage);

$("#add-btn").onclick = () => openTransaction();
$("#income-btn").onclick = () => openTransaction(null, "income");
// N: new expense, I: new income (when not typing).
document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, textarea, select, dialog") || e.metaKey || e.ctrlKey) return;
  const kind = { n: "expense", i: "income" }[e.key.toLowerCase()];
  if (kind) {
    e.preventDefault();
    openTransaction(null, kind);
  }
});

await loadSettings(() => {
  load();
  if (location.hash === "#outlook") renderOutlook();
});
showPage();
load();
