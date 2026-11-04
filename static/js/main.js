// Starts the page: settings and the current page (overview, #history or #outlook).
import "./bank-import.js";
import "./data.js";
import { renderHistory } from "./history.js";
import { renderOutlook } from "./outlook.js";
import { load } from "./overview.js";
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
