// The History page: looking back on a year, month by month (calculated by the server,
// GET /api/history): income, spending, the result, and the bank and savings balances.
import { lineChart } from "./chart.js";
import { escapeHtml, money, monthName, monthOnly } from "./format.js";
import { $, api, columnTips, tipHead } from "./ui.js";

// In January nothing of the new year is finished yet, so start on last year.
let year = new Date().getFullYear() - (new Date().getMonth() === 0 ? 1 : 0);
let range = { first: year, last: year };

const signed = (v) => `${v < 0 ? "−" : "+"}${money(Math.abs(v))}`;
const COLUMN_TIPS = {
  Income: "Income booked in that month.",
  Spent: "Everything spent that month, inside and outside your budgets.",
  Result: "Income minus spending: what the month added, or took.",
  "Bank account": "The expected balance at the end of the month (today, for this month), from your starting point on.",
  Savings: "The expected savings at the end of the month (today, for this month), from your starting point on.",
};

export async function renderHistory() {
  const h = await api(`/api/history?year=${year}`);
  range = { first: h.first_year, last: h.last_year };
  $("#history-year").textContent = year;
  $("#history-prev").disabled = year <= range.first;
  $("#history-next").disabled = year >= range.last;

  // Only finished months: the one you're in is on the Overview until it's over.
  const done = h.months.length;
  $("#history-note").textContent = !done ? `No finished months in ${year} yet. This month is on the Overview until it's over.`
    : `${done === 12 ? "The whole year" : done === 1 ? monthOnly(h.months[0].month, "long") : `${monthOnly(h.months[0].month, "long")} – ${monthOnly(h.months[done - 1].month, "long")}`}. ${
      year === range.last ? "This month is added once it's over." : ""}`;
  renderBudgets(h.budgets);
  ["#history-summary", "#history-chart-card", "#history-table-card"].forEach((s) => ($(s).hidden = !done));
  const { totals } = h;
  const tile = (label, value, note = "", cls = "") =>
    `<div class="tile ${cls}"><span class="label">${label}</span><span class="tile-value">${value}</span>${note ? `<span class="muted">${note}</span>` : ""}</div>`;
  $("#history-summary").innerHTML = [
    tile("Income", money(totals.income)),
    tile("Spent", money(totals.spent)),
    tile("Result", signed(totals.net), totals.net < 0 ? "More spent than earned" : "Left after income and spending"),
    tile("Savings", totals.savings_change === null ? "—" : signed(totals.savings_change),
      totals.savings_change === null ? "Set a starting point for your savings to see this" : `Change over these months`),
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
      { name: "Savings", values: savings, cls: "line" },
      { name: "Bank account", values: bank, cls: "line bank", dotCls: "bank" },
    ], {
      includeZero: true,
      bars: { values: values("net"), label: "Month" },
      tooltip: (i) => {
        const r = row(months[i]);
        return `<b>${monthName(months[i])}</b><span>${signed(r.net)} this month</span>
          ${r.savings === null ? "" : `<span class="tip-layer">Savings <b>${money(r.savings)}</b></span>`}
          ${r.bank === null ? "" : `<span class="tip-layer">Bank account <b>${money(r.bank)}</b></span>`}`;
      },
    });
  }

  const cell = (v, cls = "") => `<td class="${cls}">${v === null ? "—" : money(v)}</td>`;
  $("#history-table").innerHTML = `
    <thead><tr>${["Month", "Income", "Spent", "Result", "Bank account", "Savings"].map((l) => tipHead(l, COLUMN_TIPS[l])).join("")}</tr></thead>
    <tbody>${[...h.months].reverse().map((r) => `<tr>
      <td>${monthOnly(r.month, "long")}</td>
      ${cell(r.income)}${cell(r.spent)}<td class="${r.net < 0 ? "neg" : ""}">${signed(r.net)}</td>${cell(r.bank)}${cell(r.savings)}
    </tr>`).join("")}</tbody>`;
}

// Each budget line per month: a bar for how much of what it had was spent, and per line the
// totals and whether it's usually over budget (or usually has a lot left).
function renderBudgets(b) {
  $("#history-budgets-card").hidden = !b.groups.length && !b.outside;
  if (!b.groups.length && !b.outside) return;
  const head = `<thead><tr>${tipHead("Budget", "")}${b.months.map((m) => `<th class="bh-month">${monthOnly(m)}</th>`).join("")}
    ${tipHead("Spent of budgeted", "What was spent in these months, against their budgets added up (without leftovers carried over).")}</tr></thead>`;
  // A small column per month: full when what there was to spend is used up, red when more was spent.
  // Without a budget, the bars compare the months with each other (the highest is full).
  const bar = (m, r, top) => {
    if (!r) return `<td class="bh-month"></td>`;
    const tip = (lines) => `data-tip="${escapeHtml(lines.join("\n"))}" tabindex="0"`;
    if (r.budget === null) {
      return `<td class="bh-month" ${tip([monthName(m), `${money(r.spent)} spent`, "No budget"])}><span class="bh-col none"><i style="height:${top ? Math.round((r.spent / top) * 100) : 0}%"></i></span></td>`;
    }
    const over = r.spent > r.available;
    const fill = over || r.available <= 0 ? (r.spent > 0 ? 100 : 0) : Math.round((r.spent / r.available) * 100);
    const lines = [monthName(m), `${money(r.spent)} spent of ${money(r.available)}`,
      over ? `${money(r.spent - r.available)} over` : `${money(r.available - r.spent)} left`];
    if (r.available !== r.budget) lines.push(`Budget ${money(r.budget)}, plus carry-over and extra`);
    return `<td class="bh-month${over ? " over" : ""}" ${tip(lines)}><span class="bh-col${over ? " over" : ""}"><i style="height:${fill}%"></i></span></td>`;
  };
  const TAGS = {
    over: (l) => `<span class="bh-tag over" title="More was spent than budgeted in ${l.over_budget} of ${l.budgeted_months} months, and more than budgeted in total. Consider a higher budget.">Usually over</span>`,
    under: () => `<span class="bh-tag under" title="Never over budget, and on average more than a quarter left. The budget could be lower.">Usually money left</span>`,
  };
  const row = (l, name, cls) => {
    const diff = l.budget - l.spent;
    const total = l.budgeted_months
      ? `${money(l.spent, { whole: true })} <span class="muted">of ${money(l.budget, { whole: true })}</span>
         <span class="bh-diff ${diff < 0 ? "neg" : ""}">${diff < 0 ? `${money(-diff, { whole: true })} over` : `${money(diff, { whole: true })} left`}</span>`
      : `${money(l.spent, { whole: true })} <span class="bh-diff muted">no budget</span>`;
    return `<tr class="bh-line ${cls}">
      <td class="bh-name">${escapeHtml(name)}${l.pattern ? TAGS[l.pattern](l) : ""}</td>
      ${b.months.map((m) => bar(m, l.months[m], Math.max(0, ...Object.values(l.months).map((r) => r.spent)))).join("")}
      <td class="bh-total">${total}</td></tr>`;
  };
  const body = b.groups.map((g) => {
    const single = g.lines.length === 1 && g.lines[0].key === `c${g.id}`;
    if (single) return row(g.lines[0], g.name, "single");
    return `<tr class="bh-cat"><td colspan="${b.months.length + 2}">${escapeHtml(g.name)}</td></tr>` + g.lines.map((l) => row(l, l.name, "")).join("");
  }).join("");
  const outside = b.outside ? row(b.outside, "Uncategorized", "single outside") : "";
  $("#history-budgets").innerHTML = head + `<tbody>${body}${outside}</tbody>`;
}

$("#history-prev").onclick = () => { year--; renderHistory(); };
$("#history-next").onclick = () => { year++; renderHistory(); };
columnTips($("#history-table"));
columnTips($("#history-budgets"));
document.addEventListener("data-changed", () => $("#history-view").hidden || renderHistory());
