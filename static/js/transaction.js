// The transaction dialog: add or edit an expense, income or savings transfer. Expenses
// and income can be split over several budgets; the dialog previews each budget's effect.
import { combobox, datePicker } from "./controls.js";
import {
  currencySymbol, currentMonth, escapeHtml, inputAmount, isoDate, money, monthName, monthOnly, parseAmount,
} from "./format.js";
import { load, monthData } from "./overview.js";
import { isTransfer, lineBody, splitKey, state, uncategorized } from "./state.js";
import { $, api, confirmDialog, toast } from "./ui.js";

const form = $("#add-form");
let editing = null; // the transaction being edited, or null when adding
let kind = "expense"; // "expense", "income", or a transfer: "save" (to savings) or "withdraw"
let splitMode = false;
let dialogData = null; // month data for the month of the transaction's date

const isTransferKind = () => kind === "save" || kind === "withdraw";

async function loadDialogMonth() {
  dialogData = await monthData(form.date.value.slice(0, 7));
  updateSplits();
  renderLeftoverHint();
}

const date = datePicker($("#date-btn"), form.date, { onChange: loadDialogMonth });
// Optional: the day the money actually left the bank, e.g. a bill for next month paid in advance.
const paidDate = datePicker($("#paid-btn"), form.paid_date);
function showPaidDate(value) {
  $("#paid-row").hidden = !value;
  $("#paid-toggle").hidden = !!value;
  if (value) paidDate.set(value);
  else form.paid_date.value = "";
}
$("#paid-toggle").onclick = () => showPaidDate(form.date.value);
$("#paid-clear").onclick = () => showPaidDate(null);

// Choices: the budget lines that apply in the transaction's month.
function budgetOptions() {
  const categories = dialogData?.categories || state.data.categories;
  const standalone = categories.filter((c) => !c.items.length && c.budget !== null).map((c) => ({ value: `c${c.id}`, label: c.name }));
  const items = categories.flatMap((c) => c.items.filter((i) => i.budget !== null)
    .map((i) => ({ value: `i${i.id}`, label: i.name, group: c.name, display: `${c.name} · ${i.name}` })));
  return [...standalone, ...items];
}

const payee = combobox(form.payee, {
  options: () => state.payees.filter((p) => p.kind === kind).map((p) => ({ value: p.name, label: p.name, line: p.line })),
  // Picking a known payee pre-selects the budget used for them last time.
  onSelect: (o) => {
    const rows = splitRows();
    if (!splitMode && o.line && rows[0].combo.value === null) rows[0].combo.set(o.line);
    clearError("payee");
    updateSplits();
  },
});

const splitRows = () => [...document.querySelectorAll(".split")];
const nonePlaceholder = () => (splitMode ? (kind === "income" ? "Not added to a budget" : "Uncategorized") : "Choose a budget");
function addSplitRow(line = null, amount = "") {
  const row = document.createElement("div");
  row.className = "split";
  row.innerHTML = `<input class="split-line" placeholder="${nonePlaceholder()}" aria-label="Budget">
    <input class="split-amount" inputmode="decimal" placeholder="Amount" aria-label="Amount for this budget" value="${amount}">
    <button type="button" class="delete remove-split" aria-label="Remove part">×</button>`;
  $("#splits").append(row);
  row.combo = combobox(row.querySelector(".split-line"), { options: budgetOptions, strict: true, empty: "No budget with that name", onSelect: updateSplits });
  if (line) row.combo.set(line);
  return row;
}

// The parts as [{ line (null = uncategorized), amount (cents; NaN = not filled in) }].
function currentParts() {
  const total = parseAmount(form.amount.value);
  if (!splitMode) return [{ line: splitRows()[0].combo.value, amount: total }];
  const parts = splitRows().map((r) => ({ line: r.combo.value, amount: r.querySelector(".split-amount").value.trim() }));
  const filled = parts.reduce((sum, p) => sum + (parseAmount(p.amount) || 0), 0);
  const empty = parts.filter((p) => p.amount === "");
  // One empty amount gets the rest of the total.
  return parts.map((p) => ({ line: p.line, amount: p.amount === "" ? (empty.length === 1 ? total - filled : NaN) : parseAmount(p.amount) }));
}

// Show amounts only when splitting, hint at what's left, and preview each budget afterwards.
function updateSplits() {
  $("#splits").classList.toggle("single", !splitMode);
  // Only when it changes: this also runs when a field loses focus, which happens during
  // a mouse press, and Safari cancels a click on a button whose text was just replaced.
  const label = splitMode ? "+ Add another part" : kind === "income" ? "+ Divide over budgets" : "+ Split across budgets";
  if ($("#add-split").textContent !== label) $("#add-split").textContent = label;
  const total = parseAmount(form.amount.value) || 0;
  const rest = total - splitRows().reduce((sum, r) => sum + (parseAmount(r.querySelector(".split-amount").value) || 0), 0);
  splitRows().forEach((r) => (r.querySelector(".split-amount").placeholder = rest > 0 ? `Rest ${inputAmount(rest)}` : "Amount"));
  renderImpact();
}

function renderImpact() {
  if (!dialogData) return;
  const ym = dialogData.month;
  // The transaction being edited is already in the month's numbers: take it out.
  const own = { spent: {}, extra: {} };
  if (editing && editing.date.slice(0, 7) === ym) {
    const target = editing.kind === "income" ? own.extra : editing.kind === "expense" ? own.spent : null;
    if (target) for (const s of editing.splits) target[splitKey(s)] = (target[splitKey(s)] || 0) + s.amount;
  }
  const lines = dialogData.groups.flatMap((g) => g.lines.map((l) => ({ ...l, label: g.has_items ? `${g.name} · ${l.name}` : g.name })));
  const rows = [];
  let unassigned = 0;
  for (const p of currentParts()) {
    if (!(p.amount > 0)) continue;
    if (!p.line) { unassigned += p.amount; continue; }
    const line = lines.find((l) => l.key === p.line);
    if (!line || line.budget === null) continue;
    const base = line.available - (own.extra[p.line] || 0);
    const used = line.spent - (own.spent[p.line] || 0);
    // An expense uses up budget; income adds to it.
    const [availAfter, after] = kind === "income" ? [base + p.amount, used] : [base, used + p.amount];
    const leftText = (s, a) => (s > a ? `${money(s - a)} over` : `${money(a - s)} left`);
    rows.push(`<div class="impact-row ${after > availAfter ? "over" : ""}">
      <span class="name">${escapeHtml(line.label)}${ym !== state.month ? ` <span class="muted">· ${monthOnly(ym)}</span>` : ""}</span>
      <span>${leftText(used, base)} → <b>${leftText(after, availAfter)}</b></span>
      <div class="bar"><span style="width:${availAfter ? Math.min(100, (after / availAfter) * 100) : 100}%"></span></div>
    </div>`);
  }
  if (unassigned > 0) rows.push(`<div class="impact-row muted"><span>${money(unassigned)} ${kind === "income" ? "not added to a budget" : "uncategorized"}</span></div>`);
  // Always show something here, so the form doesn't jump while typing.
  if (!rows.length) {
    rows.push(`<div class="impact-row muted"><span>${kind === "income"
      ? "Enter an amount to see how it adds to a budget" : "Enter an amount to see how it affects your budget"}</span></div>`);
  }
  $("#impact").innerHTML = rows.join("");
}

// What part of the month's unspent budget can go to savings: next month is covered first.
async function renderLeftoverHint() {
  if (!dialogData || kind !== "save") return ($("#leftover-hint").innerHTML = "");
  const ym = form.date.value.slice(0, 7);
  const o = (await monthData(ym, editing?.id)).outlook;
  const saveable = o.balance === null ? o.rest : o.saveable;
  const parts = [`Unspent budget in ${monthName(ym)} that isn't carried over: <b>${money(o.unspent)}</b>`];
  if (o.saved) parts.push(`already saved ${money(o.saved)}`);
  if (o.keep_for_next) parts.push(`${money(o.keep_for_next)} is needed for ${monthOnly(o.next, "long")}`);
  $("#leftover-hint").innerHTML = `
    <span>${parts.join(" · ")}</span>
    ${saveable > 0 ? `<button type="button" class="link-btn" id="use-leftover" data-amount="${saveable}">Use ${money(saveable)}</button>` : ""}`;
}
$("#leftover-hint").onclick = (e) => {
  const btn = e.target.closest("#use-leftover");
  if (!btn) return;
  form.amount.value = inputAmount(Number(btn.dataset.amount));
  clearError("amount");
};

$("#add-split").onclick = () => {
  if (!splitMode) {
    splitMode = true;
    // The existing part keeps the full amount until another one takes some of it.
    if (parseAmount(form.amount.value) > 0) splitRows()[0].querySelector(".split-amount").value = form.amount.value.trim();
  }
  addSplitRow().querySelector(".split-line").focus();
  updateSplits();
};
$("#splits").onclick = (e) => {
  if (!e.target.matches(".remove-split")) return;
  e.target.closest(".split").remove();
  if (splitRows().length === 1) {
    splitMode = false;
    splitRows()[0].querySelector(".split-amount").value = "";
  }
  updateSplits();
};
form.addEventListener("input", (e) => {
  clearError(e.target.name || (e.target.closest(".split") ? "splits" : ""));
  updateSplits();
});
form.addEventListener("focusout", updateSplits);
form.amount.addEventListener("blur", () => {
  if (form.amount.value.trim() && !(parseAmount(form.amount.value) > 0)) showError("amount", "Enter the amount as a number, like 12,50.");
});

function showError(name, message) {
  const el = form.querySelector(`[data-error="${name}"]`);
  el.textContent = message;
  el.closest(".field").classList.add("invalid");
}
function clearError(name) {
  const el = name && form.querySelector(`[data-error="${name}"]`);
  if (!el) return;
  el.textContent = "";
  el.closest(".field").classList.remove("invalid");
}

// Labels and fields that differ between expenses, income and savings transfers.
function applyKind() {
  const income = kind === "income", transfer = isTransferKind();
  const noun = transfer ? "transfer" : income ? "income" : "expense";
  document.querySelectorAll("#kind-options button").forEach((b) => b.classList.toggle("active", b.dataset.kind === (transfer ? "transfer" : kind)));
  document.querySelectorAll("#direction-options button").forEach((b) => b.classList.toggle("active", b.dataset.direction === kind));
  $("#transfer-field").hidden = !transfer;
  $("#payee-field").hidden = transfer;
  $("#budget-field").hidden = transfer;
  renderLeftoverHint();
  $("#expense-title").textContent = editing ? `Edit ${noun}` : `New ${noun}`;
  $("#expense-submit").textContent = editing ? "Save changes" : `Add ${noun}`;
  $("#payee-label").textContent = income ? "Received from" : "Paid to";
  form.payee.placeholder = income ? "e.g. Employer, Marktplaats" : "e.g. Albert Heijn";
  $("#budget-label").textContent = income ? "Add to budget" : "Budget";
  splitRows().forEach((r) => (r.querySelector(".split-line").placeholder = nonePlaceholder()));
  clearError("payee");
  updateSplits();
}
$("#kind-options").onclick = (e) => {
  if (!e.target.dataset.kind) return;
  kind = e.target.dataset.kind === "transfer" ? "save" : e.target.dataset.kind;
  applyKind();
};
$("#direction-options").onclick = (e) => {
  if (!e.target.dataset.direction) return;
  kind = e.target.dataset.direction;
  applyKind();
};

// Opens the dialog for `transaction`, or for a new one of `newKind` with optional preset
// values: { amount (cents), date, description }.
export async function openTransaction(transaction = null, newKind = "expense", preset = {}) {
  editing = transaction;
  kind = transaction?.kind || newKind;
  form.reset();
  form.querySelectorAll("[data-error]").forEach((el) => clearError(el.dataset.error));
  $("#splits").innerHTML = "";
  $("#kind-options").hidden = !!transaction;
  $("#expense-delete").hidden = !transaction;
  $("#expense-dialog .currency").textContent = currencySymbol();

  if (transaction) {
    form.amount.value = inputAmount(transaction.amount);
    form.payee.value = transaction.payee;
    form.description.value = transaction.description;
    date.set(transaction.date);
    showPaidDate(transaction.paid_date);
  } else {
    payee.clear();
    showPaidDate(null);
    // Default to today when viewing this month, else the 1st of the viewed month.
    date.set(preset.date || (state.month === currentMonth() ? isoDate(new Date()) : `${state.month}-01`));
    if (preset.amount) form.amount.value = inputAmount(preset.amount);
    if (preset.description) form.description.value = preset.description;
  }
  dialogData = await monthData(form.date.value.slice(0, 7));

  // One part covering the whole amount is shown simply; anything else as split parts.
  const splits = transaction?.splits || [];
  const rest = transaction ? uncategorized(transaction) : 0;
  splitMode = splits.length > 1 || (splits.length === 1 && rest > 0);
  if (!splitMode) {
    addSplitRow(splits[0] ? splitKey(splits[0]) : null);
  } else {
    for (const s of splits) addSplitRow(splitKey(s), inputAmount(s.amount));
    if (rest > 0) addSplitRow(null, inputAmount(rest));
  }
  applyKind();
  $("#expense-dialog").showModal();
  form.amount.focus();
}

form.onsubmit = async (e) => {
  e.preventDefault();
  const total = parseAmount(form.amount.value);
  const parts = currentParts();
  const transfer = isTransferKind();
  const invalid = [];
  if (!form.amount.value.trim()) invalid.push(["amount", kind === "income" ? "Enter the amount you received." : transfer ? "Enter the amount to move." : "Enter the amount you paid."]);
  else if (!(total > 0)) invalid.push(["amount", "Enter an amount above zero, like 12,50."]);
  if (!payee.value && !transfer) invalid.push(["payee", kind === "income" ? "Enter who paid you." : "Enter who you paid."]);
  if (splitMode && total > 0 && !transfer) {
    const sum = parts.reduce((s, p) => s + (p.amount || 0), 0);
    if (parts.some((p) => Number.isNaN(p.amount))) invalid.push(["splits", "Enter an amount for each part. You can leave one empty: it gets the rest."]);
    else if (parts.some((p) => !(p.amount > 0))) invalid.push(["splits", "Each part needs an amount above zero. Remove parts you don't need with ×."]);
    else if (sum > total) invalid.push(["splits", `The parts add up to ${money(sum)}, which is more than the ${money(total)} total. Lower one of the parts.`]);
  }
  if (invalid.length) {
    invalid.forEach(([name, message]) => showError(name, message));
    form.querySelector(".field.invalid input, .field.invalid .split-line")?.focus();
    return;
  }

  const body = {
    kind, date: form.date.value, paid_date: form.paid_date.value || null, amount: total, payee: payee.value, description: form.description.value,
    // Parts without a budget stay uncategorized: whatever the splits don't cover.
    splits: transfer ? [] : parts.filter((p) => p.line).map((p) => ({ ...lineBody(p.line), amount: p.amount })),
  };
  if (editing) await api(`/api/transactions/${editing.id}`, { method: "PUT", body });
  else await api("/api/transactions", { method: "POST", body });
  $("#expense-dialog").close();
  toast(editing ? "Changes saved"
    : transfer ? `Moved ${money(total)} ${kind === "save" ? "to" : "from"} savings`
    : kind === "income" ? `Added ${money(total)} from ${payee.value}` : `Added ${money(total)} at ${payee.value}`);
  state.month = form.date.value.slice(0, 7);
  load();
};

$("#expense-delete").onclick = async () => {
  const noun = isTransfer(editing) ? "transfer" : editing.kind === "income" ? "income" : "expense";
  if (!(await confirmDialog({
    title: `Delete this ${noun}?`, message: "It's removed for good. Your budgets and balances update right away.",
    confirm: "Delete", danger: true,
  }))) return;
  await api(`/api/transactions/${editing.id}`, { method: "DELETE" });
  $("#expense-dialog").close();
  toast(`Deleted ${noun}`);
  load();
};
