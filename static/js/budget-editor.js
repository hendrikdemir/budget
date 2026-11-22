// The "Edit budgets" dialog. Edits apply from the viewed month onward; earlier months
// keep their budgets. Changes are saved as soon as a field loses focus.
//
// At the top it shows whether the budgets fit the income (GET /api/budget-fit), and lets the
// user enter their monthly income there. Without any budgets yet, it suggests common ones to
// start from: fill in an amount for the ones you need.
import { currencySymbol, escapeHtml, example, inputAmount, money, monthName, parseAmount } from "./format.js";
import { helpTip } from "./help.js";
import { t } from "./i18n.js";
import { load } from "./overview.js";
import { isSimple, state } from "./state.js";
import { $, api, confirmDialog, fieldError, once, toast } from "./ui.js";

const FIRST_MONTH = "0000-01"; // budgets that have applied since the start
const PLUS = `<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`;
const CARRY_TIP = t("budgets.carryByDefault");

// A few common budgets to start from: fixed costs as one category with items, then budgets of their own.
const STARTERS = () => [
  { name: t("budgets.fixedCosts"), items: [t("budgets.rentOrMortgage"), t("budgets.energyAndWater"), t("budgets.insurance"), t("budgets.phoneAndInternet")] },
  { name: t("budgets.groceries") },
  { name: t("budgets.transport") },
  { name: t("budgets.funMoney") },
];

// Show lines that apply this month, plus ones with changes planned from this month on.
const relevant = (line) => line.budget !== null || line.history.some((h) => h.start_month >= state.month);

function historyChips(line) {
  const changes = line.history;
  if (changes.length < 2 && line.budget !== null) return "";
  const current = changes.filter((h) => h.start_month <= state.month).at(-1);
  return `<div class="history">${changes.map((h) => `
    <span class="hchip ${h === current ? "current" : ""}">
      ${h.start_month === FIRST_MONTH ? t("budgets.fromTheStart") : t("common.from", { month: monthName(h.start_month, "short") })}:
      ${h.amount === null ? t("budgets.ended") : money(h.amount) + (h.rollover ? " ↪" : "")}
      ${changes.length > 1 ? `<button type="button" class="undo" data-budget="${h.id}" aria-label="${t("common.removeThisChange")}">×</button>` : ""}
    </span>`).join("")}</div>`;
}

// Column headings above the list, each lined up with the text in its column. Carry over is one of
// the features beyond the basics: hidden with only the basics, but keeping its place.
const columnHeadings = () => `<div class="mgr-row mgr-labels">
  <span class="label">${t("budgets.columnName")}</span>
  <span class="label mgr-label-amount">${t("budgets.columnAmount")}</span>
  <button type="button" class="label help-label full-only" data-help="carry" title="${CARRY_TIP}">${t("common.carryOver")}</button>
  <span></span>
</div>`;

function lineRow(kind, line, { withBudget = true } = {}) {
  const ended = line.budget === null;
  return `<div class="mgr-row ${kind === "category" ? "mgr-head" : "mgr-item"} ${withBudget && ended ? "ended" : ""}" data-kind="${kind}" data-id="${line.id}">
    <input class="name" value="${escapeHtml(line.name)}" aria-label="${t("common.name")}" data-focus="${kind}${line.id}n">
    ${withBudget ? `
      <input class="amount" inputmode="decimal" value="${ended ? "" : inputAmount(line.budget)}" placeholder="${t("budgets.endedPlaceholder")}" aria-label="${t("budgets.monthlyBudget")}" data-focus="${kind}${line.id}a">
      <label class="carry-default full-only" title="${CARRY_TIP}">
        <input type="checkbox" class="rollover" ${line.rollover ? "checked" : ""} ${ended ? "disabled" : ""} data-focus="${kind}${line.id}r">
      </label>`
      : "<span></span><span></span>"}
    <button type="button" class="delete remove" aria-label="${t("budgets.remove")}">×</button>
    ${withBudget ? historyChips(line) : ""}
  </div>`;
}

function render() {
  $("#manager-month").textContent = monthName(state.month);
  const focused = document.activeElement?.dataset?.focus;
  const shown = state.data.categories.filter((c) => relevant(c) || c.items.some(relevant));
  $("#manager-body").innerHTML = (shown.length ? columnHeadings() : "") +
    shown.map((c) => `
        <div class="mgr-cat" data-id="${c.id}">
          ${lineRow("category", c, { withBudget: c.single || !c.items.length })}
          ${c.items.filter(relevant).map((i) => lineRow("item", i)).join("")}
          <form class="mgr-row add-item">
            <input name="name" placeholder="${c.items.length ? t("budgets.newItem") : t("budgets.splitIntoItemsEG")}" required>
            <input name="budget" inputmode="decimal" placeholder="${t("common.budget")}">
            <label class="carry-default full-only" title="${CARRY_TIP}"><input type="checkbox" name="rollover" aria-label="${t("budgets.carryLeftovers")}"></label>
            <button class="icon-btn" aria-label="${t("budgets.addItem")}">${PLUS}</button>
          </form>
        </div>`).join("");
  renderStarter(!state.data.categories.length);
  if (focused) $(`[data-focus="${focused}"]`)?.focus();
}

// ---- Income and budgets: do they fit? ----
let fit = null;
async function renderFit() {
  fit = await api(`/api/budget-fit?month=${state.month}`);
  const starting = !$("#starter").hidden;
  const budgets = fit.budgets + (starting ? starterTotal() : 0);
  const left = fit.income - budgets - fit.planned;
  const incomeRow = fit.income_plans === 0
    ? `${incomeField("fit-income-form", t("budgets.yourIncomePerMonth"), "")}
      <p class="muted fit-why">${t("budgets.yourSalaryBenefitsOrAllowance")}</p>`
    : `<div class="fit-row"><span>${t("budgets.incomeIn", { month: monthName(state.month) })}</span>
        <span class="fit-amount">${money(fit.income)}${fit.plan
          ? ` <button type="button" class="link-btn" id="fit-income-change">${t("budgets.change")}</button>`
          : isSimple() ? "" : ` <a class="link-btn" href="#outlook" data-close-manager>${t("budgets.inTheOutlook")}</a>`}</span></div>`;
  if (fit.income_plans === 0 && !budgets) {
    $("#budget-fit").innerHTML = incomeRow;
    return bindFit();
  }
  const rows = [incomeRow,
    `<div class="fit-row"><span>${t("common.budgets")}</span><span class="fit-amount">− ${money(budgets)}</span></div>`];
  if (fit.planned) rows.push(`<div class="fit-row"><span>${t("budgets.plannedCostsInTheOutlook")}</span><span class="fit-amount">− ${money(fit.planned)}</span></div>`);
  if (fit.income_plans > 0) {
    rows.push(`<div class="fit-row fit-result ${left < 0 ? "short" : ""}">
      <span>${left < 0 ? t("budgets.moreThanYourIncome") : t("budgets.leftToSaveOrPlan")} ${helpTip("fit")}</span>
      <span class="fit-amount">${left < 0 ? `− ${money(-left)}` : money(left)}</span></div>`);
    if (left < 0) rows.push(`<p class="fit-note">${t("budgets.yourBudgetsAddUpTo")}</p>`);
  }
  if (fit.spending && !fit.budgets) {
    rows.push(`<p class="muted fit-why">${t("budgets.averageSpending", { count: fit.spending.months, amount: money(fit.spending.average) })}</p>`);
  }
  $("#budget-fit").innerHTML = rows.join("");
  bindFit();
}
// The income field saves itself, like the budgets below it: when it's left after a change, or
// with Enter. Without an income yet it adds one; otherwise it changes it from this month on.
const incomeField = (id, label, value) => `<form class="fit-income" id="${id}" novalidate>
  <label class="field"><span class="label">${label}</span>
    <span class="money-input"><span class="currency"></span><input name="amount" inputmode="decimal" value="${value}" placeholder="${example("0.00")}"></span>
    <span class="error" data-error="amount"></span></label>
</form>`;
function bindIncome(form, body) {
  const original = form.amount.value;
  form.onsubmit = (e) => {
    e.preventDefault();
    form.amount.blur(); // saved by the change event, so Enter and leaving the field save once
  };
  form.amount.onchange = once(async () => {
    const text = form.amount.value.trim();
    if (text === "") return;
    const amount = parseAmount(text);
    if (!(amount > 0)) return fieldError(form, "amount", t("common.enterAnAmountAboveZero", { example: example("2500.00") }));
    await api("/api/income", { method: "PUT", body: { month: state.month, amount, ...body } });
    toast(t("budgets.incomeSaved"));
    renderFit();
    document.dispatchEvent(new Event("data-changed"));
  });
  // Left without changing it: show the amount again instead of the field.
  form.amount.onblur = () => setTimeout(() => form.isConnected && form.amount.value === original && original !== "" && renderFit());
  form.oninput = () => fieldError(form, "amount", "");
}
function bindFit() {
  $("#budget-fit").querySelectorAll(".currency").forEach((el) => (el.textContent = currencySymbol()));
  const form = $("#fit-income-form");
  if (form) bindIncome(form, { name: t("common.income") });
  const change = $("#fit-income-change");
  if (change) change.onclick = changeIncome;
  $("#budget-fit").querySelector("[data-close-manager]")?.addEventListener("click", () => $("#manager").close());
}
// The one monthly income, from this month on, in place.
function changeIncome() {
  $("#fit-income-change").closest(".fit-row").outerHTML =
    incomeField("fit-change-form", t("budgets.incomePerMonthFrom", { month: monthName(state.month) }), inputAmount(fit.income));
  bindFit();
  const form = $("#fit-change-form");
  bindIncome(form, { plan_id: fit.plan.id });
  form.amount.select();
}

// ---- Starting budgets ----
const starterRows = () => [...$("#starter").querySelectorAll(".starter-row")];
const starterTotal = () => starterRows().reduce((sum, r) => sum + (parseAmount(r.querySelector(".amount").value) || 0), 0);
let starterShown = false;
function renderStarter(empty) {
  $("#starter").hidden = !empty;
  $("#add-category").hidden = empty;
  if (!empty) return (starterShown = false);
  if (starterShown) return;
  starterShown = true;
  $("#starter").innerHTML = `
    <p class="starter-intro"><b>${t("budgets.startWithCommonBudgets")}</b>
      <span class="muted">${t("budgets.fillInAnAmountPer")}</span></p>
    ${STARTERS().map((group) => `<div class="starter-group">${group.items
      ? `<div class="mgr-row mgr-head starter-head"><input class="name group-name" value="${escapeHtml(group.name)}" aria-label="${t("common.name")}"></div>
        ${group.items.map((name) => starterRow(name, "mgr-item")).join("")}`
      : starterRow(group.name, "mgr-head")}</div>`).join("")}
    <div class="starter-group">${starterRow("", "mgr-head", t("budgets.somethingElseEGPets"))}</div>
    <p class="error" id="starter-error"></p>
    <div class="starter-foot">
      <button type="button" class="link-btn" id="starter-skip">${t("budgets.startEmpty")}</button>
      <span class="spacer"></span>
      <button type="button" class="primary-btn" id="starter-add" disabled>${t("budgets.addBudgets")}</button>
    </div>`;
  updateStarter();
}
function starterRow(name, cls, placeholder = "") {
  return `<div class="mgr-row ${cls} starter-row">
    <input class="name" value="${escapeHtml(name)}" ${placeholder ? `placeholder="${escapeHtml(placeholder)}"` : ""} aria-label="${t("common.name")}">
    <input class="amount" inputmode="decimal" placeholder="${t("common.amount")}" aria-label="${name ? t("budgets.monthlyBudgetFor", { name: escapeHtml(name) }) : t("budgets.monthlyBudget")}">
  </div>`;
}
// The budget lines with an amount filled in: [{ name, text, group (the category's name, for an item) }].
function chosenStarters() {
  return starterRows().map((r) => ({
    name: r.querySelector(".name").value.trim(), text: r.querySelector(".amount").value.trim(),
    group: r.closest(".starter-group").querySelector(".group-name")?.value.trim() ?? null,
  })).filter((r) => r.text !== "");
}
function updateStarter() {
  const n = chosenStarters().length;
  const label = n ? t("budgets.addCount", { count: n }) : t("budgets.addBudgets");
  if ($("#starter-add").textContent !== label) $("#starter-add").textContent = label; // see transaction.js: WebKit and changed buttons
  $("#starter-add").disabled = !n;
  $("#starter-error").textContent = "";
}
let fitTimer;
$("#starter").addEventListener("input", () => {
  updateStarter();
  clearTimeout(fitTimer);
  fitTimer = setTimeout(renderFit, 250); // the income comparison follows the amounts being typed
});
$("#starter").addEventListener("click", once(async (e) => {
  if (e.target.id === "starter-skip") {
    $("#starter").hidden = true;
    $("#add-category").hidden = false;
    $("#add-category").name.focus();
    return renderFit();
  }
  if (e.target.id !== "starter-add") return;
  const chosen = chosenStarters();
  const wrong = chosen.find((r) => !r.name || r.group === "" || !(parseAmount(r.text) > 0));
  if (wrong) {
    $("#starter-error").textContent = wrong.name
      ? t("budgets.enterTheAmountForAs", { name: wrong.name, example: example("250.00") })
      : t("budgets.giveEachBudgetWithAn");
    return;
  }
  // Items go into their category, in the order shown; other lines are budgets of their own.
  const budgets = [];
  for (const r of chosen) {
    if (r.group === null) budgets.push({ name: r.name, budget: parseAmount(r.text) });
    else {
      let category = budgets.find((b) => b.items && b.name === r.group);
      if (!category) budgets.push((category = { name: r.group, items: [] }));
      category.items.push({ name: r.name, budget: parseAmount(r.text) });
    }
  }
  await api("/api/starter-budgets", { method: "POST", body: { month: state.month, budgets } });
  // Done setting up: back to the overview, which now shows the new budgets.
  $("#manager").close();
  toast(t("budgets.addedCount", { count: chosen.length }));
  load();
}));

async function refresh() {
  await load();
  render();
  renderFit();
}
export function openManager() {
  starterShown = false;
  render();
  renderFit();
  $("#manager").showModal();
}
// Income can also change in the plan dialog, opened from here or the Outlook.
document.addEventListener("data-changed", () => $("#manager").open && renderFit());

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
      title: t("budgets.removeFromOnward", { name, month: monthName(state.month) }),
      message: t("budgets.earlierMonthsKeepTheirBudget"),
      confirm: t("budgets.remove"), danger: true,
    });
    if (!ok) return;
    await api(`/api/${row.dataset.kind === "item" ? "items" : "categories"}/${row.dataset.id}?month=${state.month}`, { method: "DELETE" });
  } else return;
  refresh();
};
