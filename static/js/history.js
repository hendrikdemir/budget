// The History page: looking back on a year, month by month (calculated by the server,
// GET /api/history): income, spending, the result, and the bank and savings balances.
import { lineChart } from "./chart.js";
import { cap, escapeHtml, money, monthName, monthOnly } from "./format.js";
import { t } from "./i18n.js";
import { $, api, columnTips, tipHead } from "./ui.js";

// In January nothing of the new year is finished yet, so start on last year.
let year = new Date().getFullYear() - (new Date().getMonth() === 0 ? 1 : 0);
let range = { first: year, last: year };

const signed = (v) => `${v < 0 ? "−" : "+"}${money(Math.abs(v))}`;
const COLUMN_TIPS = () => ({
  Income: t("history.incomeBookedInThatMonth"),
  Spent: t("history.everythingSpentThatMonthInside"),
  Result: t("history.incomeMinusSpendingWhatThe"),
  "Bank account": t("history.theExpectedBalanceAtThe"),
  Savings: t("history.theExpectedSavingsAtThe"),
});

export async function renderHistory() {
  const h = await api(`/api/history?year=${year}`);
  range = { first: h.first_year, last: h.last_year };
  $("#history-year").textContent = year;
  $("#history-prev").disabled = year <= range.first;
  $("#history-next").disabled = year >= range.last;

  // Only finished months: the one you're in is on the Overview until it's over.
  const done = h.months.length;
  $("#history-note").hidden = !done;
  $("#history-empty").hidden = !!done;
  $("#history-empty p").textContent = h.empty
    ? t("history.nothingToLookBackOn")
    : t("history.noFinishedMonthsInYet", { year });
  $("#history-note").textContent = !done ? "" : `${done === 12 ? t("history.theWholeYear") : cap(done === 1 ? monthOnly(h.months[0].month, "long") : `${monthOnly(h.months[0].month, "long")} – ${monthOnly(h.months[done - 1].month, "long")}`)}. ${
      year === range.last ? t("history.thisMonthIsAddedOnce") : ""}`;
  renderBudgets(h.budgets);
  ["#history-summary", "#history-chart-card", "#history-table-card"].forEach((s) => ($(s).hidden = !done));
  const { totals } = h;
  const tile = (label, value, note = "", cls = "") =>
    `<div class="tile ${cls}"><span class="label">${label}</span><span class="tile-value">${value}</span>${note ? `<span class="muted">${note}</span>` : ""}</div>`;
  $("#history-summary").innerHTML = [
    tile(t("common.income"), money(totals.income)),
    tile(t("common.spent"), money(totals.spent)),
    tile(t("common.result"), signed(totals.net), totals.net < 0 ? t("common.moreSpentThanEarned") : t("common.leftAfterIncomeAndSpending")),
    tile(t("history.savings"), totals.savings_change === null ? "—" : signed(totals.savings_change),
      totals.savings_change === null ? t("history.setAStartingBalanceFor") : t("history.changeOverTheseMonths")),
  ].join("");

  // From the first tracked month to December, with the ones still to come left empty.
  const from = Number(h.months[0]?.month.slice(5) ?? 1);
  const months = Array.from({ length: 13 - from }, (_, i) => `${year}-${String(from + i).padStart(2, "0")}`);
  const row = (m) => h.months.find((r) => r.month === m);
  const values = (key) => months.map((m) => row(m)?.[key] ?? null);
  const savings = values("savings"), bank = values("bank");
  const tracked = savings.some((v) => v !== null) || bank.some((v) => v !== null);
  $("#history-chart").hidden = !tracked;
  $("#history-chart-empty").hidden = tracked;
  if (tracked) {
    lineChart($("#history-chart"), months, [
      { name: t("history.savings"), values: savings, cls: "line" },
      { name: t("common.bankAccount"), values: bank, cls: "line bank", dotCls: "bank" },
    ], {
      includeZero: true,
      bars: { values: values("net"), label: t("common.month") },
      tooltip: (i) => {
        const r = row(months[i]);
        return `<b>${cap(monthName(months[i]))}</b><span>${t("common.thisMonth", { amount: signed(r.net) })}</span>
          ${r.savings === null ? "" : `<span class="tip-layer">${t("history.savings")} <b>${money(r.savings)}</b></span>`}
          ${r.bank === null ? "" : `<span class="tip-layer">${t("common.bankAccount")} <b>${money(r.bank)}</b></span>`}`;
      },
    });
  }

  const cell = (v, cls = "") => `<td class="${cls}">${v === null ? "—" : money(v)}</td>`;
  const tips = COLUMN_TIPS();
  $("#history-table").innerHTML = `
    <thead><tr>${[[t("common.month")], [t("common.income"), tips.Income], [t("common.spent"), tips.Spent], [t("common.result"), tips.Result],
      [t("common.bankAccount"), tips["Bank account"]], [t("history.savings"), tips.Savings]].map(([label, tip]) => tipHead(label, tip)).join("")}</tr></thead>
    <tbody>${[...h.months].reverse().map((r) => `<tr>
      <td>${cap(monthOnly(r.month, "long"))}</td>
      ${cell(r.income)}${cell(r.spent)}<td class="${r.net < 0 ? "neg" : ""}">${signed(r.net)}</td>${cell(r.bank)}${cell(r.savings)}
    </tr>`).join("")}</tbody>`;
}

// Each budget line per month: a bar for how much of what it had was spent, and per line the
// totals and whether it's usually over budget (or usually has a lot left).
function renderBudgets(b) {
  $("#history-budgets-card").hidden = !b.groups.length && !b.outside;
  if (!b.groups.length && !b.outside) return;
  const head = `<thead><tr>${tipHead(t("common.budget"), "")}${b.months.map((m) => `<th class="bh-month">${cap(monthOnly(m))}</th>`).join("")}
    ${tipHead(t("history.spentOfBudgeted"), t("history.whatWasSpentInThese"))}</tr></thead>`;
  // A small column per month: full when what there was to spend is used up, red when more was spent.
  // Without a budget, the bars compare the months with each other (the highest is full).
  const bar = (m, r, top) => {
    if (!r) return `<td class="bh-month"></td>`;
    const tip = (lines) => `data-tip="${escapeHtml(lines.join("\n"))}" tabindex="0"`;
    if (r.budget === null) {
      return `<td class="bh-month" ${tip([cap(monthName(m)), t("history.spent", { amount: money(r.spent) }), t("common.noBudget")])}><span class="bh-col none"><i style="height:${top ? Math.round((r.spent / top) * 100) : 0}%"></i></span></td>`;
    }
    const over = r.spent > r.available;
    const fill = over || r.available <= 0 ? (r.spent > 0 ? 100 : 0) : Math.round((r.spent / r.available) * 100);
    const lines = [cap(monthName(m)), t("common.spentOf", { spent: money(r.spent), budget: money(r.available) }),
      over ? t("common.over", { amount: money(r.spent - r.available) }) : t("common.left", { amount: money(r.available - r.spent) })];
    if (r.available !== r.budget) lines.push(t("history.budgetPlusCarryOverAnd", { amount: money(r.budget) }));
    return `<td class="bh-month${over ? " over" : ""}" ${tip(lines)}><span class="bh-col${over ? " over" : ""}"><i style="height:${fill}%"></i></span></td>`;
  };
  const TAGS = {
    over: (l) => `<span class="bh-tag over" title="${t("history.moreWasSpentThanBudgeted", { over: l.over_budget, months: l.budgeted_months })}">${t("history.usuallyOver")}</span>`,
    under: () => `<span class="bh-tag under" title="${t("history.neverOverBudgetAndOn")}">${t("history.usuallyMoneyLeft")}</span>`,
  };
  const row = (l, name, cls) => {
    const diff = l.budget - l.spent;
    const total = l.budgeted_months
      ? `${money(l.spent, { whole: true })} <span class="muted">${t("common.of", { amount: money(l.budget, { whole: true }) })}</span>
         <span class="bh-diff ${diff < 0 ? "neg" : ""}">${diff < 0 ? t("common.over", { amount: money(-diff, { whole: true }) }) : t("common.left", { amount: money(diff, { whole: true }) })}</span>`
      : `${money(l.spent, { whole: true })} <span class="bh-diff muted">${t("history.noBudget")}</span>`;
    return `<tr class="bh-line ${cls}">
      <td class="bh-name">${escapeHtml(name)}${l.pattern ? TAGS[l.pattern](l) : ""}</td>
      ${b.months.map((m) => bar(m, l.months[m], Math.max(0, ...Object.values(l.months).map((r) => r.spent)))).join("")}
      <td class="bh-total">${total}</td></tr>`;
  };
  const body = b.groups.map((g) => {
    const single = g.lines.length === 1 && g.lines[0].key === `c${g.id}`;
    if (single) return row(g.lines[0], g.name, "single");
    return `<tr class="bh-cat"><td colspan="${b.months.length + 2}">${escapeHtml(g.name)}</td></tr>` + g.lines.map((l) => row(l, l.name ?? t("history.asOneBudget"), "")).join("");
  }).join("");
  const outside = b.outside ? row(b.outside, t("common.noBudget"), "single outside") : "";
  $("#history-budgets").innerHTML = head + `<tbody>${body}${outside}</tbody>`;
}

$("#history-prev").onclick = () => { year--; renderHistory(); };
$("#history-next").onclick = () => { year++; renderHistory(); };
columnTips($("#history-table"));
columnTips($("#history-budgets"));
document.addEventListener("data-changed", () => $("#history-view").hidden || renderHistory());
