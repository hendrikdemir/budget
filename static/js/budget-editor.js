// The "Edit budgets" dialog. Edits apply from the viewed month onward; earlier months
// keep their budgets. Changes are saved as soon as a field loses focus.
import { escapeHtml, inputAmount, money, monthName, parseAmount } from "./format.js";
import { load } from "./overview.js";
import { state } from "./state.js";
import { $, api, confirmDialog, once } from "./ui.js";

const FIRST_MONTH = "0000-01"; // budgets that have applied since the start
const PLUS = `<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`;

// Show lines that apply this month, plus ones with changes planned from this month on.
const relevant = (line) => line.budget !== null || line.history.some((h) => h.start_month >= state.month);

function historyChips(line) {
  const changes = line.history;
  if (changes.length < 2 && line.budget !== null) return "";
  const current = changes.filter((h) => h.start_month <= state.month).at(-1);
  return `<div class="history">${changes.map((h) => `
    <span class="hchip ${h === current ? "current" : ""}">
      ${h.start_month === FIRST_MONTH ? "From start" : `From ${monthName(h.start_month, "short")}`}:
      ${h.amount === null ? "ended" : money(h.amount) + (h.rollover ? " ↪" : "")}
      ${changes.length > 1 ? `<button type="button" class="undo" data-budget="${h.id}" aria-label="Remove this change">×</button>` : ""}
    </span>`).join("")}</div>`;
}

function lineRow(kind, line, { withBudget = true } = {}) {
  const ended = line.budget === null;
  return `<div class="mgr-row ${kind === "category" ? "mgr-head" : "mgr-item"} ${withBudget && ended ? "ended" : ""}" data-kind="${kind}" data-id="${line.id}">
    <input class="name" value="${escapeHtml(line.name)}" aria-label="Name" data-focus="${kind}${line.id}n">
    ${withBudget ? `
      <input class="amount" inputmode="decimal" value="${ended ? "" : inputAmount(line.budget)}" placeholder="Ended" aria-label="Monthly budget" data-focus="${kind}${line.id}a">
      <label class="carry-default" title="Carry leftovers to next month by default">
        <input type="checkbox" class="rollover" ${line.rollover ? "checked" : ""} ${ended ? "disabled" : ""} data-focus="${kind}${line.id}r">
      </label>`
      : "<span></span><span></span>"}
    <button type="button" class="delete remove" aria-label="Remove">×</button>
    ${withBudget ? historyChips(line) : ""}
  </div>`;
}

function render() {
  $("#manager-month").textContent = monthName(state.month);
  const focused = document.activeElement?.dataset?.focus;
  $("#manager-body").innerHTML = `
    <div class="mgr-row mgr-labels"><span></span><span>Budget</span><span title="Carry leftovers to next month by default">Carry</span><span></span></div>` +
    state.data.categories
      .filter((c) => relevant(c) || c.items.some(relevant))
      .map((c) => `
        <div class="mgr-cat" data-id="${c.id}">
          ${lineRow("category", c, { withBudget: c.single || !c.items.length })}
          ${c.items.filter(relevant).map((i) => lineRow("item", i)).join("")}
          <form class="mgr-row add-item">
            <input name="name" placeholder="${c.items.length ? "New item" : "Split into items, e.g. Electricity"}" required>
            <input name="budget" inputmode="decimal" placeholder="Budget">
            <label class="carry-default" title="Carry leftovers to next month by default"><input type="checkbox" name="rollover" aria-label="Carry leftovers to next month"></label>
            <button class="icon-btn" aria-label="Add item">${PLUS}</button>
          </form>
        </div>`).join("");
  if (focused) $(`[data-focus="${focused}"]`)?.focus();
}
async function refresh() {
  await load();
  render();
}
export function openManager() {
  render();
  $("#manager").showModal();
}

$("#add-category").onsubmit = once(async (e) => {
  e.preventDefault();
  const f = e.target;
  await api("/api/categories", { method: "POST", body: { name: f.name.value, budget: parseAmount(f.budget.value) || 0, rollover: f.rollover.checked, month: state.month } });
  f.reset();
  refresh();
});

const body = $("#manager-body");
body.onsubmit = once(async (e) => {
  e.preventDefault();
  const f = e.target;
  const categoryId = Number(f.closest(".mgr-cat").dataset.id);
  await api("/api/items", { method: "POST", body: { category_id: categoryId, name: f.name.value, budget: parseAmount(f.budget.value) || 0, rollover: f.rollover.checked, month: state.month } });
  await refresh();
  body.querySelector(`.mgr-cat[data-id="${categoryId}"] .add-item input`).focus();
});
body.onchange = async (e) => {
  const row = e.target.closest(".mgr-row[data-kind]");
  if (!row) return;
  const { kind, id } = row.dataset;
  const amount = row.querySelector(".amount")?.value.trim();
  const line = { [`${kind}_id`]: Number(id), month: state.month };
  try {
    if (e.target.classList.contains("name")) {
      await api(`/api/${kind === "item" ? "items" : "categories"}/${id}`, { method: "PUT", body: { name: e.target.value } });
    } else if (e.target.classList.contains("rollover")) {
      await api("/api/budgets", { method: "PUT", body: { ...line, amount: parseAmount(amount), rollover: e.target.checked } });
    } else if (amount !== "") {
      await api("/api/budgets", { method: "PUT", body: { ...line, amount: parseAmount(amount) } });
    }
  } finally {
    refresh();
  }
};
body.onclick = async (e) => {
  const undo = e.target.closest(".undo");
  const remove = e.target.closest(".remove");
  if (undo) {
    await api(`/api/budgets/${undo.dataset.budget}`, { method: "DELETE" });
  } else if (remove) {
    const row = remove.closest(".mgr-row");
    const name = row.querySelector(".name").value;
    const ok = await confirmDialog({
      title: `Remove “${name}” from ${monthName(state.month)} onward?`,
      message: "Earlier months keep their budget and spending. If it was never used, it is deleted completely. Add it again with the same name to bring it back.",
      confirm: "Remove", danger: true,
    });
    if (!ok) return;
    await api(`/api/${row.dataset.kind === "item" ? "items" : "categories"}/${row.dataset.id}?month=${state.month}`, { method: "DELETE" });
  } else return;
  refresh();
};
