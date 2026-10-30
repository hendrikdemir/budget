// The Outlook page: the savings projection (calculated by the server, GET /api/projection)
// and the plans it's based on: expected income and planned extra expenses.
import { lineChart } from "./chart.js";
import { monthPicker } from "./controls.js";
import { currencySymbol, currentMonth, escapeHtml, inputAmount, money, monthName, monthOnly, parseAmount, shiftMonth } from "./format.js";
import { $, api, confirmDialog, fieldError, toast } from "./ui.js";

let plans = [];

export async function renderOutlook() {
  const [projection, allPlans] = await Promise.all([api("/api/projection"), api("/api/plans")]);
  plans = allPlans;
  renderPlans();
  $("#outlook-chart-card").hidden = !projection.visible;
  $("#outlook-table").closest(".card").hidden = !projection.visible;
  if (!projection.visible) {
    $("#outlook-summary").innerHTML = `<p class="muted">Set up the balance of your bank account and savings on the overview to see your outlook.</p>`;
    return;
  }
  const { rows } = projection;
  const lowName = monthName(projection.low_month);
  const below = projection.low_above < 0;
  $("#outlook-summary").innerHTML = `
    <div class="tile"><span class="label">Savings today</span><span class="tile-value">${money(projection.savings_today)}</span></div>
    <div class="tile"><span class="label">After ${monthOnly(rows[1].month, "long")}'s budget</span><span class="tile-value">${money(rows[0].savings)}</span></div>
    <div class="tile ${below ? "short" : "ok"}">
      <span class="label">${below ? "Below your buffer" : "Free to spend"}</span>
      <span class="tile-value">${money(below ? -projection.low_above : rows[0].free)}</span>
      <span class="muted">${below
        ? `Your savings drop below one month's budget from ${monthName(projection.first_below)}${projection.first_below !== projection.low_month
          ? `, down to ${money(-projection.low_above)} below it in ${lowName}` : ""}.`
        : `Lowest point in the next year is ${lowName}, so this much can go without dipping below your buffer.`}</span>
    </div>`;

  const cell = (v, cls = "") => `<td class="${cls}">${v === undefined ? "—" : money(v)}</td>`;
  $("#outlook-table").innerHTML = `
    <thead><tr><th>Month</th><th>Income</th><th>Budget</th><th>Planned</th><th>Result</th><th>Savings</th><th>Free to spend</th></tr></thead>
    <tbody>${rows.map((r) => `<tr class="${r.now ? "now" : ""} ${r.month === projection.low_month ? "low" : ""}">
      <td>${monthName(r.month, "short")}${r.now ? ` <span class="muted">now</span>` : ""}</td>
      ${cell(r.income)}${cell(r.budget)}${r.planned ? cell(r.planned) : `<td>${r.now ? "—" : ""}</td>`}
      ${cell(r.result, r.result < 0 ? "neg" : "")}${cell(r.savings, r.above < 0 ? "neg" : "")}${cell(r.free, r.free === 0 ? "muted" : "")}
    </tr>`).join("")}</tbody>`;

  const months = rows.map((r) => r.month);
  const savings = rows.map((r) => r.savings), buffer = rows.map((r) => r.buffer);
  lineChart($("#outlook-chart"), months, [
    { name: "Savings", values: savings, cls: "line", against: buffer },
    { name: "Buffer", values: buffer, cls: "line dashed", dots: false },
  ], {
    includeZero: true,
    tooltip: (i) => `<b>${monthName(months[i])}</b><span>Savings: ${money(savings[i])}</span><span>Buffer: ${money(buffer[i])}</span>`,
  });
}

// ---- Plans (expected income and planned expenses) ----
function planPeriod(p) {
  const short = (m) => monthName(m, "short");
  if (p.end_month === p.start_month) return short(p.start_month);
  return p.end_month ? `Monthly, ${short(p.start_month)} – ${short(p.end_month)}` : `Monthly from ${short(p.start_month)}`;
}
function renderPlans() {
  for (const kind of ["income", "expense"]) {
    const list = plans.filter((p) => p.kind === kind);
    $(`#plans-${kind}`).innerHTML = list.length
      ? list.map((p) => `<li data-plan="${p.id}" tabindex="0">
          <span class="plan-name">${escapeHtml(p.name)}</span>
          <span class="muted">${planPeriod(p)}${p.changes.map((c) => ` · ${money(c.amount)} from ${monthName(c.start_month, "short")}`).join("")}</span>
          <span class="plan-amount">${money(p.amount)}</span>
        </li>`).join("")
      : `<li class="plan-empty muted">${kind === "income" ? "No expected income yet. Add your salary and other regular income." : "No planned expenses."}</li>`;
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
  const show = editingPlan && planRepeat === "monthly";
  $("#plan-changes-field").hidden = !show;
  if (!show) return;
  $("#change-month").textContent = `From ${monthName(changeMonth, "short")}`;
  $("#plan-changes").innerHTML = [`<span class="hchip">From ${monthName(editingPlan.start_month, "short")}: ${money(editingPlan.amount)}</span>`]
    .concat(editingPlan.changes.map((c) => `<span class="hchip">From ${monthName(c.start_month, "short")}: ${money(c.amount)}
      <button type="button" class="undo" data-change="${c.id}" aria-label="Remove this change">×</button></span>`)).join("");
}
async function reloadPlan() {
  plans = await api("/api/plans");
  editingPlan = plans.find((p) => p.id === editingPlan.id);
  renderPlanChanges();
  renderOutlook();
}
$("#change-add").onclick = async () => {
  const amount = parseAmount($("#change-amount").value);
  if (!(amount > 0)) return fieldError(planForm, "change", "Enter the new amount, like 1700,00.");
  if (changeMonth <= editingPlan.start_month) return fieldError(planForm, "change", `Choose a month after ${monthName(editingPlan.start_month)}, when this plan starts.`);
  await api("/api/plan-changes", { method: "POST", body: { plan_id: editingPlan.id, start_month: changeMonth, amount } });
  $("#change-amount").value = "";
  fieldError(planForm, "change", "");
  toast(`${editingPlan.name}: ${money(amount)} from ${monthName(changeMonth)}`);
  reloadPlan();
};
$("#plan-changes").onclick = async (e) => {
  const btn = e.target.closest("[data-change]");
  if (!btn) return;
  await api(`/api/plan-changes/${btn.dataset.change}`, { method: "DELETE" });
  reloadPlan();
};

function renderPlanDates() {
  $("#plan-start").textContent = monthName(planStart);
  $("#plan-end").textContent = planEnd ? monthName(planEnd) : "No end";
  $("#plan-no-end").hidden = !planEnd;
  $("#plan-end-field").hidden = planRepeat === "once";
  $("#plan-start-label").firstChild.textContent = planRepeat === "once" ? "Month " : "From ";
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
  $("#plan-title").textContent = `${plan ? "Edit" : "Add"} ${planKind === "income" ? "expected income" : "planned expense"}`;
  planForm.name.placeholder = planKind === "income" ? "e.g. Salary" : "e.g. Tuition fee";
  $("#plan-delete").hidden = !plan;
  planStart = plan?.start_month || shiftMonth(currentMonth(), 1);
  planEnd = plan?.end_month || null;
  planRepeat = plan ? (plan.end_month === plan.start_month ? "once" : "monthly") : planKind === "income" ? "monthly" : "once";
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
planForm.oninput = (e) => fieldError(planForm, e.target.name, "");
planForm.onsubmit = async (e) => {
  e.preventDefault();
  const amount = parseAmount(planForm.amount.value);
  let ok = true;
  if (!planForm.name.value.trim()) { fieldError(planForm, "name", "Give it a name, like Salary."); ok = false; }
  if (!(amount > 0)) { fieldError(planForm, "amount", "Enter an amount above zero, like 1234,56."); ok = false; }
  const end = planRepeat === "once" ? planStart : planEnd;
  if (end && end < planStart) { fieldError(planForm, "end", "The end month is before the start month. Choose a later one."); ok = false; }
  if (!ok) return;
  const body = { kind: planKind, name: planForm.name.value, amount, start_month: planStart, end_month: end };
  await api(editingPlan ? `/api/plans/${editingPlan.id}` : "/api/plans", { method: editingPlan ? "PUT" : "POST", body });
  $("#plan-dialog").close();
  toast(editingPlan ? "Plan updated" : "Plan added");
  renderOutlook();
};
$("#plan-delete").onclick = async () => {
  if (!(await confirmDialog({
    title: `Delete “${editingPlan.name}”?`, message: "It's no longer included in your outlook. Your transactions aren't affected.",
    confirm: "Delete", danger: true,
  }))) return;
  await api(`/api/plans/${editingPlan.id}`, { method: "DELETE" });
  $("#plan-dialog").close();
  renderOutlook();
};
$("#plan-no-end").onclick = () => { planEnd = null; renderPlanDates(); };
