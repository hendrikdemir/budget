// The History page: looking back on a year, month by month (calculated by the server,
// GET /api/history): income, spending, the result, and the bank and savings balances.
import { lineChart } from "./chart.js";
import { money, monthName, monthOnly } from "./format.js";
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
    : `${done === 12 ? "The whole year" : `${monthOnly(h.months[0].month, "long")} – ${monthOnly(h.months[done - 1].month, "long")}`}. ${
      year === range.last ? "This month is added once it's over." : ""}`;
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

  // Twelve months, with the ones still to come left empty.
  const months = Array.from({ length: 12 }, (_, i) => `${year}-${String(i + 1).padStart(2, "0")}`);
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

$("#history-prev").onclick = () => { year--; renderHistory(); };
$("#history-next").onclick = () => { year++; renderHistory(); };
columnTips($("#history-table"));
document.addEventListener("data-changed", () => $("#history-view").hidden || renderHistory());
