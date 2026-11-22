// The Outlook page: the savings projection (calculated by the server, GET /api/projection)
// and the plans it's based on: expected income and planned extra expenses.
import { lineChart } from "./chart.js";
import { monthPicker } from "./controls.js";
import { cap, currencySymbol, currentMonth, example, inputAmount, isoDate, money, monthName, monthOnly, parseAmount, shiftMonth } from "./format.js";
import { helpTip } from "./help.js";
import { element, html, setHtml } from "./html.js";
import { t } from "./i18n.js";
import { openTransaction } from "./transaction.js";
import { $, api, columnTips, confirmDialog, fieldError, once, tipHead, toast } from "./ui.js";

let plans = [], incomeTotal = null;
// Stay current when a transaction is added from this page.
document.addEventListener("data-changed", () => $("#outlook-view").hidden || renderOutlook());
let buffer = { mode: "months", months: 1, amount: 0 }; // how much should stay in savings

export async function renderOutlook() {
  const [projection, allPlans, total] = await Promise.all([api("/api/projection"), api("/api/plans"), api("/api/income-total")]);
  plans = allPlans;
  incomeTotal = total;
  renderPlans();
  $("#outlook-chart-card").hidden = !projection.visible;
  $("#outlook-table").closest(".card").hidden = !projection.visible;
  if (!projection.visible) {
    setHtml($("#outlook-summary"), html`<p class="muted">${t("outlook.setUpTheBalanceOf")}</p>`);
    return;
  }
  const { rows } = projection;
  buffer = projection.buffer;
  $("#buffer-label").textContent = t("outlook.safetyBuffer", { buffer: bufferText() });
  const lowName = monthName(projection.low_month);
  const below = projection.low_above < 0;
  // Only when savings are needed for next month does it explain anything to show them go down.
  const fromSavings = projection.next_month.short_if_spent > 0;
  $("#outlook-summary").classList.toggle("two-tiles", !fromSavings);
  setHtml($("#outlook-summary"), html`
    <div class="tile"><span class="label">${t("outlook.savingsToday")}</span><span class="tile-value">${money(projection.savings_today)}</span></div>
    ${fromSavings ? html`<div class="tile"><span class="label">${t("outlook.afterSBudget", { month: monthOnly(rows[1].month, "long") })}</span><span class="tile-value">${money(rows[0].savings)}</span></div>` : ""}
    <div class="tile ${below ? "short" : "ok"}">
      <span class="label">${below ? t("outlook.belowYourSafetyBuffer") : t("outlook.freeToSpend")} ${helpTip(below ? "buffer" : "free")}</span>
      <span class="tile-value">${money(below ? -projection.low_above : rows[0].free)}</span>
      <span class="muted">${below
        ? (projection.first_below !== projection.low_month
          ? t("outlook.dropsBelowFromTo", { month: monthName(projection.first_below), amount: money(-projection.low_above), low: lowName })
          : t("outlook.dropsBelowFrom", { month: monthName(projection.first_below) }))
        : t("outlook.lowestPointInTheNext", { month: lowName })}</span>
    </div>${fromSavingsNotice(projection.next_month)}`);
  if ($("#outlook-take")) {
    $("#outlook-take").onclick = () => openTransaction(null, "withdraw", {
      amount: projection.next_month.short_if_spent, date: isoDate(new Date()), description: t("common.for", { month: monthName(projection.next_month.month) }),
    });
  }

  const cell = (v, cls = "") => html`<td class="${cls}">${v === undefined ? "—" : money(v)}</td>`;
  const tips = COLUMN_TIPS();
  const columns = [[t("common.month")], [t("common.income"), tips.Income], [t("common.budget"), tips.Budget], [t("outlook.planned"), tips.Planned],
    [t("common.result"), tips.Result], [t("outlook.expectedSavings"), tips["Expected savings"]], [t("outlook.freeToSpend"), tips["Free to spend"]]];
  setHtml($("#outlook-table"), html`
    <thead><tr>${columns.map(([label, tip]) => tipHead(label, tip))}</tr></thead>
    <tbody>${rows.map((r) => html`<tr class="${r.now ? "now" : ""} ${r.month === projection.low_month ? "low" : ""}">
      <td>${cap(monthName(r.month, "short"))}${r.now ? html` <span class="muted">${t("outlook.now")}</span>` : ""}</td>
      ${cell(r.income)}${cell(r.budget)}${r.planned ? cell(r.planned) : html`<td></td>`}
      ${cell(r.result, r.result < 0 ? "neg" : "")}${cell(r.savings, r.above < 0 ? "neg" : "")}${cell(r.free, r.free === 0 ? "muted" : "")}
    </tr>`)}</tbody>`);

  // The chart shows where "free to spend" comes from: the gap between the line and the buffer
  // at its lowest point. The bars show what each month adds or takes.
  const months = rows.map((r) => r.month);
  const savings = rows.map((r) => r.savings), buffers = rows.map((r) => r.buffer);
  const low = months.indexOf(projection.low_month);
  const signed = (v) => `${v < 0 ? "−" : "+"}${money(Math.abs(v))}`;
  lineChart($("#outlook-chart"), months, [
    { name: t("outlook.expectedSavings"), values: savings, cls: "line", against: buffers },
    { name: t("outlook.safetyBufferTitle"), values: buffers, cls: "line dashed", dots: false },
  ], {
    includeZero: true,
    marker: { i: low, from: savings[low], to: buffers[low], cls: below ? "bad" : "",
      label: below ? t("outlook.markerBelowBuffer", { amount: money(-projection.low_above) }) : t("outlook.markerFreeToSpend", { amount: money(rows[0].free) }) },
    bars: { values: rows.map((r) => r.result), label: t("common.month") },
    tooltip: (i) => html`<b>${cap(monthName(months[i]))}</b>
      <span>${i === 0 ? t("outlook.thisMonthIfTheRest", { amount: signed(rows[i].result) }) : t("common.thisMonth", { amount: signed(rows[i].result) })}</span>
      <span>${t("outlook.tipExpectedSavings", { amount: money(savings[i]) })}</span>
      ${rows[i].above < 0 ? html`<span class="tip-bad">${t("outlook.belowYourSafetyBufferOf", { amount: money(-rows[i].above), buffer: money(buffers[i]) })}</span>`
        : html`<span class="tip-layer">${t("outlook.freeToSpend")} <b>${money(rows[i].free)}</b></span>
          <span class="tip-layer">${t("outlook.neededLater")} <b>${money(rows[i].later)}</b></span>
          <span class="tip-layer">${t("outlook.safetyBufferTitle")} <b>${money(buffers[i])}</b></span>`}
      ${i === low ? html`<span class="muted">${below ? t("outlook.lowestPointBelowYourSafety", { amount: money(-projection.low_above) })
        : t("outlook.lowestPointAboveYourSafety", { amount: money(projection.low_above) })}</span>` : ""}`,
  });
}

// What each column of the month-by-month table means, shown when hovering its header.
const COLUMN_TIPS = () => ({
  Income: t("outlook.expectedIncomeFromYourPlans"),
  Budget: t("outlook.theMonthsBudgetNextMonths"),
  Planned: t("outlook.plannedCostsOutsideYourBudgets"),
  Result: t("outlook.incomeMinusBudgetAndPlanned"),
  "Expected savings": t("outlook.yourSavingsOnceEachMonths"),
  "Free to spend": t("outlook.whatYouCanTakeOut"),
});
columnTips($("#outlook-table"));

// When the bank won't hold next month's budget, the rest has to come from savings. The
// amounts are the same as in "Ready for next month?" on the overview.
function fromSavingsNotice({ month, short, short_if_spent: ifSpent, awaiting_income: awaiting }) {
  if (ifSpent <= 0) return "";
  const name = monthOnly(month, "long"), thisMonth = monthOnly(shiftMonth(month, -1), "long");
  const alternative = ifSpent === short ? "" : short > 0
    ? ` ${t("outlook.itsIfYouDontSpend", { amount: money(short), month: thisMonth })}`
    : ` ${t("outlook.youDontNeedThisIf", { month: thisMonth })}`;
  if (awaiting) return html`<div class="result-gap ok outlook-notice">
    <div><b>${t("outlook.expectingNeededFromSavingsFor", { amount: money(ifSpent), month: name })}</b>
      <span class="muted">${t("common.youCanTakeItFrom")}${alternative}</span></div>
  </div>`;
  return html`<div class="result-gap short outlook-notice">
    <div><b>${t("outlook.neededFromSavingsFor", { amount: money(ifSpent), month: name })}</b>
      <span class="muted">${t("outlook.yourBankAccountDoesntHold", { month: name })}${alternative}</span></div>
    <button class="primary-btn" id="outlook-take">${t("common.takeFromSavings")}</button>
  </div>`;
}

// ---- Savings buffer ----
function bufferText() {
  if (buffer.mode === "amount") return money(buffer.amount);
  if (buffer.months === 1) return t("outlook.oneMonthsBudget");
  return t("outlook.monthsOfBudget", { n: example(String(buffer.months)) });
}

const bufferForm = $("#buffer-form");
let bufferMode = "months";
function renderBufferMode() {
  document.querySelectorAll("#buffer-mode button").forEach((b) => b.classList.toggle("active", b.dataset.mode === bufferMode));
  $("#buffer-months-field").hidden = bufferMode !== "months";
  $("#buffer-amount-field").hidden = bufferMode !== "amount";
}
$("#buffer-edit").onclick = () => {
  bufferMode = buffer.mode;
  bufferForm.months.value = example(String(buffer.months));
  bufferForm.amount.value = inputAmount(buffer.amount);
  fieldError(bufferForm, "months", "");
  fieldError(bufferForm, "amount", "");
  $("#buffer-dialog .currency").textContent = currencySymbol();
  renderBufferMode();
  $("#buffer-dialog").showModal();
  bufferForm[bufferMode].select();
};
$("#buffer-mode").onclick = (e) => {
  if (!e.target.dataset.mode) return;
  bufferMode = e.target.dataset.mode;
  renderBufferMode();
  bufferForm[bufferMode].select();
};
bufferForm.oninput = (e) => fieldError(bufferForm, e.target.name, "");
bufferForm.onsubmit = once(async (e) => {
  e.preventDefault();
  const value = parseAmount(bufferForm[bufferMode].value); // months are parsed like amounts: "1.5" -> 150
  if (!(value >= 0)) {
    return fieldError(bufferForm, bufferMode, bufferMode === "months" ? t("outlook.enterANumberOfMonths", { example: example("1.5") }) : t("outlook.enterAnAmountLike", { example: example("2500.00") }));
  }
  await api("/api/buffer", { method: "PUT", body: bufferMode === "months" ? { mode: "months", months: value / 100 } : { mode: "amount", amount: value } });
  $("#buffer-dialog").close();
  toast(t("outlook.safetyBufferUpdated"));
  renderOutlook();
});

// ---- Plans (expected income and planned expenses) ----
function planPeriod(p) {
  const short = (m) => monthName(m, "short");
  if (p.end_month === p.start_month) return short(p.start_month);
  const how = p.every_months > 1 ? t("outlook.everyMonths", { n: p.every_months }) : t("outlook.monthly");
  return p.end_month ? `${how}, ${short(p.start_month)} – ${short(p.end_month)}` : t("outlook.from", { how, month: short(p.start_month) });
}
// The months a plan falls in, from `start` every `every` months until `end` (at most `max`).
function planMonths(start, end, every, max = 24) {
  const found = [];
  for (let m = start; (!end || m <= end) && found.length < max; m = shiftMonth(m, every)) found.push(m);
  return found;
}
const everyValue = () => Number(planForm.every.value.trim());
function renderPlans() {
  for (const kind of ["income", "expense"]) {
    const list = plans.filter((p) => p.kind === kind);
    setHtml($(`#plans-${kind}`), list.length
      ? html`${list.map((p) => html`<li data-plan="${p.id}" tabindex="0">
          <span class="plan-name">${p.name}</span>
          <span class="muted">${planPeriod(p)}${p.changes.map((c) => ` · ${t("outlook.amountFrom", { amount: money(c.amount), month: monthName(c.start_month, "short") })}`)}</span>
          <span class="plan-amount">${money(p.amount)}</span>
        </li>`)}`
      : html`<li class="plan-empty muted">${kind === "income" ? t("outlook.noExpectedIncomeYetAdd") : t("outlook.noPlannedExpenses")}</li>`);
  }
  // Total expected income this month, with the next month it changes.
  const total = incomeTotal;
  if (total && plans.filter((p) => p.kind === "income").length > 1) {
    $("#plans-income").append(element(html`<li class="plan-total">
      <span class="plan-name">${t("outlook.total")}</span>
      <span class="muted">${total.change ? t("outlook.amountFrom", { amount: money(total.change.amount), month: monthName(total.change.month, "short") }) : ""}</span>
      <span class="plan-amount">${money(total.amount)}</span>
    </li>`));
  }
}

const planForm = $("#plan-form");
let editingPlan = null, planKind = "income", planRepeat = "monthly", planStart = currentMonth(), planEnd = null;
monthPicker($("#plan-start"), { get: () => planStart, set: (m) => { planStart = m; renderPlanDates(); } });
monthPicker($("#plan-end"), { get: () => planEnd || planStart, set: (m) => { planEnd = m; renderPlanDates(); } });

// Amount changes of a saved monthly plan, saved right away (like budget changes).
let changeMonth = currentMonth();
monthPicker($("#change-month"), { get: () => changeMonth, set: (m) => { changeMonth = m; renderPlanChanges(); } });
function renderPlanChanges() {
  // Only for monthly plans: a custom one has one amount, just spread over chosen months.
  const show = editingPlan && planRepeat === "monthly";
  $("#plan-changes-field").hidden = !show;
  if (!show) return;
  $("#change-month").textContent = t("common.from", { month: monthName(changeMonth, "short") });
  setHtml($("#plan-changes"), html`<span class="hchip">${t("common.from", { month: monthName(editingPlan.start_month, "short") })}: ${money(editingPlan.amount)}</span>
    ${editingPlan.changes.map((c) => html`<span class="hchip">${t("common.from", { month: monthName(c.start_month, "short") })}: ${money(c.amount)}
      <button type="button" class="undo" data-change="${c.id}" aria-label="${t("common.removeThisChange")}">×</button></span>`)}`);
}
async function reloadPlan() {
  [plans, incomeTotal] = await Promise.all([api("/api/plans"), api("/api/income-total")]);
  editingPlan = plans.find((p) => p.id === editingPlan.id);
  renderPlanChanges();
  renderOutlook();
}
$("#change-add").onclick = once(async () => {
  const amount = parseAmount($("#change-amount").value);
  if (!(amount > 0)) return fieldError(planForm, "change", t("outlook.enterTheNewAmountLike", { example: example("1700.00") }));
  if (changeMonth <= editingPlan.start_month) return fieldError(planForm, "change", t("outlook.chooseAMonthAfterWhen", { month: monthName(editingPlan.start_month) }));
  await api("/api/plan-changes", { method: "POST", body: { plan_id: editingPlan.id, start_month: changeMonth, amount } });
  $("#change-amount").value = "";
  fieldError(planForm, "change", "");
  toast(`${editingPlan.name}: ${t("outlook.amountFrom", { amount: money(amount), month: monthName(changeMonth) })}`);
  reloadPlan();
});
$("#plan-changes").onclick = async (e) => {
  const btn = e.target.closest("[data-change]");
  if (!btn) return;
  await api(`/api/plan-changes/${btn.dataset.change}`, { method: "DELETE" });
  reloadPlan();
};

function renderPlanDates() {
  $("#plan-start").textContent = cap(monthName(planStart));
  $("#plan-end").textContent = planEnd ? cap(monthName(planEnd)) : t("outlook.noEnd");
  $("#plan-no-end").hidden = !planEnd;
  $("#plan-end-field").hidden = planRepeat === "once";
  $("#plan-every-field").hidden = planRepeat !== "every";
  // When it falls, so it's easy to check: "4 times: Dec 2026, Feb, Apr and Jun 2027".
  const every = everyValue();
  const when = planRepeat === "every" && planEnd && Number.isInteger(every) && every >= 2 && every <= 12 && planEnd >= planStart
    ? planMonths(planStart, planEnd, every) : null;
  $("#plan-when").hidden = !when;
  if (when) {
    // The year once, after its last month in the list.
    const names = when.map((m, i) => (i === when.length - 1 || m.slice(0, 4) !== when[i + 1].slice(0, 4)
      ? monthName(m, "short") : monthOnly(m)));
    const list = names.length > 1 ? t("outlook.and", { list: names.slice(0, -1).join(", "), last: names.at(-1) }) : names[0];
    $("#plan-when").textContent = `${t("outlook.timesCount", { count: when.length })}: ${list}.`;
  }
  $("#plan-start-label").firstChild.textContent = `${planRepeat === "once" ? t("common.month") : t("outlook.fromLabel")} `;
  document.querySelectorAll("#repeat-options button").forEach((b) => b.classList.toggle("active", b.dataset.repeat === planRepeat));
  renderPlanChanges();
}
function openPlan(plan = null, kind = "income") {
  editingPlan = plan;
  planKind = plan?.kind || kind;
  planForm.reset();
  planForm.querySelectorAll("[data-error]").forEach((el) => fieldError(planForm, el.dataset.error, ""));
  $("#plan-dialog").querySelectorAll(".currency").forEach((el) => (el.textContent = currencySymbol()));
  changeMonth = shiftMonth(plan?.changes.at(-1)?.start_month || plan?.start_month || currentMonth(), 1);
  $("#change-amount").value = "";
  $("#plan-title").textContent = planKind === "income" ? (plan ? t("outlook.editExpectedIncome") : t("outlook.addExpectedIncome"))
    : plan ? t("outlook.editPlannedExpense") : t("outlook.addPlannedExpense");
  planForm.name.placeholder = planKind === "income" ? t("outlook.eGSalary") : t("outlook.eGTuitionFee");
  $("#plan-delete").hidden = !plan;
  planStart = plan?.start_month || shiftMonth(currentMonth(), 1);
  planEnd = plan?.end_month || null;
  planRepeat = plan ? (plan.end_month === plan.start_month ? "once" : plan.every_months > 1 ? "every" : "monthly")
    : planKind === "income" ? "monthly" : "once";
  planForm.every.value = plan?.every_months > 1 ? plan.every_months : 2;
  if (plan) {
    planForm.name.value = plan.name;
    planForm.amount.value = inputAmount(plan.amount);
  }
  renderPlanDates();
  $("#plan-dialog").showModal();
  planForm.name.focus();
}
$("#repeat-options").onclick = (e) => {
  if (!e.target.dataset.repeat) return;
  planRepeat = e.target.dataset.repeat;
  renderPlanDates();
};
document.querySelectorAll("[data-add-plan]").forEach((b) => (b.onclick = () => openPlan(null, b.dataset.addPlan)));
document.querySelectorAll(".plan-list").forEach((ul) => {
  ul.onclick = (e) => {
    const li = e.target.closest("[data-plan]");
    if (li) openPlan(plans.find((p) => p.id === Number(li.dataset.plan)));
  };
  ul.onkeydown = (e) => e.key === "Enter" && e.target.closest("[data-plan]")?.click();
});
planForm.oninput = (e) => {
  fieldError(planForm, e.target.name, "");
  if (e.target.name === "every") renderPlanDates();
};
planForm.onsubmit = once(async (e) => {
  e.preventDefault();
  const amount = parseAmount(planForm.amount.value);
  let ok = true;
  if (!planForm.name.value.trim()) { fieldError(planForm, "name", t("outlook.giveItANameLike")); ok = false; }
  if (!(amount > 0)) { fieldError(planForm, "amount", t("common.enterAnAmountAboveZero", { example: example("1234.56") })); ok = false; }
  const end = planRepeat === "once" ? planStart : planEnd;
  const every = planRepeat === "every" ? everyValue() : 1;
  if (!(Number.isInteger(every) && every >= 1 && every <= 12)) { fieldError(planForm, "every", t("outlook.everyRange")); ok = false; }
  if (end && end < planStart) { fieldError(planForm, "end", t("outlook.theEndMonthIsBefore")); ok = false; }
  if (!ok) return;
  const body = { kind: planKind, name: planForm.name.value, amount, start_month: planStart, end_month: end, every_months: every };
  await api(editingPlan ? `/api/plans/${editingPlan.id}` : "/api/plans", { method: editingPlan ? "PUT" : "POST", body });
  $("#plan-dialog").close();
  toast(editingPlan ? t("outlook.planUpdated") : t("outlook.planAdded"));
  renderOutlook();
  document.dispatchEvent(new Event("data-changed")); // e.g. the income in Edit budgets
});
$("#plan-delete").onclick = once(async () => {
  if (!(await confirmDialog({
    title: t("outlook.delete", { name: editingPlan.name }), message: t("outlook.itsNoLongerIncludedIn"),
    confirm: t("common.delete"), danger: true,
  }))) return;
  await api(`/api/plans/${editingPlan.id}`, { method: "DELETE" });
  $("#plan-dialog").close();
  renderOutlook();
});
$("#plan-no-end").onclick = () => { planEnd = null; renderPlanDates(); };
