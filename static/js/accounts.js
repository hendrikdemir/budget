// Bank and savings balances: the account rows on the overview and the account dialog
// (expected balance, checks against the bank, starting point, development chart).
import { lineChart } from "./chart.js";
import { datePicker } from "./controls.js";
import { currencySymbol, inputAmount, isoDate, money, monthName, monthOnly, parseAmount, shortDate } from "./format.js";
import { $, api, fieldError, toast } from "./ui.js";

const ACCOUNTS = { bank: "Bank account", savings: "Savings" };
const balances = {}; // per account: { start, start_date, expected, checks: [{ id, date, actual, expected, difference }] }
let account = "bank"; // the account open in the dialog
let historyYear = new Date().getFullYear();
const checkForm = $("#check-form");
const startForm = $("#start-form");
const checkDate = datePicker($("#check-date-btn"), checkForm.date);
const startDate = datePicker($("#start-date-btn"), startForm.date);

export async function loadBalances() {
  await Promise.all(Object.keys(ACCOUNTS).map(async (a) => (balances[a] = await api(`/api/balance?account=${a}`))));
  renderRows();
}

function differenceText(diff) {
  if (diff === 0) return "Matches";
  return diff < 0
    ? `${money(-diff)} less in your bank — a transaction may be missing`
    : `${money(diff)} more in your bank — a transaction may be missing`;
}

function renderRows() {
  for (const [a, b] of Object.entries(balances)) {
    const row = $(`.account-row[data-account="${a}"]`);
    const set = b.start !== null;
    const last = b.checks.find((c) => c.difference !== null);
    row.querySelector(".balance-amount").textContent = b.expected !== null ? money(b.expected) : set ? "—" : "Not set up";
    const status = row.querySelector(".balance-status");
    status.classList.remove("ok", "off");
    if (!set) status.textContent = "Add a starting balance to track it";
    else if (!last) status.textContent = "Expected today · not checked yet";
    else if (last.difference === 0) {
      status.textContent = `✓ Matched on ${shortDate(last.date)}`;
      status.classList.add("ok");
    } else {
      status.textContent = `${money(Math.abs(last.difference))} off on ${shortDate(last.date)}`;
      status.classList.add("off");
    }
    row.querySelector(".balance-action").textContent = set ? "Check ›" : "Set up ›";
  }
  if ($("#balance-dialog").open) renderDialog();
}

function renderDialog() {
  const b = balances[account];
  const set = b.start !== null;
  $("#balance-title").textContent = ACCOUNTS[account];
  $("#balance-summary").innerHTML = set
    ? `<span class="label">Expected today</span>
       <span class="balance-amount">${b.expected !== null ? money(b.expected) : "—"}</span>
       <span class="muted">${money(b.start)} at the start of ${shortDate(b.start_date)}, plus ${account === "bank"
         ? "income and minus expenses since, and transfers to and from savings" : "transfers to and from savings since"}.</span>`
    : `<span class="muted">Set a starting point first: the balance on a day from which you'll register everything.</span>`;
  checkForm.hidden = !set;
  $("#history").hidden = !set;
  $("#check-list").innerHTML = b.checks.map((c) => `
    <li class="${c.difference === null ? "" : c.difference === 0 ? "ok" : "off"}">
      <span class="check-date">${shortDate(c.date)}</span>
      <span class="check-actual">${money(c.actual)}</span>
      <span class="check-result">${c.difference === null ? "Before the starting point" : differenceText(c.difference)}</span>
      <button class="delete" data-check="${c.id}" aria-label="Remove this check">×</button>
    </li>`).join("");
}

// End-of-month balance through a year. Months before tracking started (or still to come) stay empty.
async function renderHistory() {
  const data = await api(`/api/balance-history?account=${account}&year=${historyYear}`);
  $("#hist-year").textContent = historyYear;
  $("#hist-next").disabled = historyYear >= new Date().getFullYear();
  // Nothing to show before the year tracking started.
  $("#hist-prev").disabled = historyYear <= Number((balances[account].start_date || String(historyYear)).slice(0, 4));
  const months = Array.from({ length: 12 }, (_, i) => `${historyYear}-${String(i + 1).padStart(2, "0")}`);
  const values = months.map((m) => data.months.find((d) => d.month === m)?.balance ?? null);
  const tracked = values.map((v, i) => ({ v, i })).filter((p) => p.v !== null);
  if (!tracked.length) {
    $("#hist-plot").innerHTML = "";
    $("#hist-change").textContent = "";
    $("#hist-note").textContent = `No balance tracked in ${historyYear}.`;
    return;
  }
  lineChart($("#hist-plot"), months, [{ name: `${ACCOUNTS[account]} balance`, values, cls: "line" }], {
    height: 170, ticks: 3,
    tooltip: (i) => {
      const before = values[i - 1] ?? null;
      return `<b>${monthName(months[i])}</b><span>${money(values[i])}</span>${before === null ? ""
        : `<span class="muted">${values[i] >= before ? "+" : "−"}${money(Math.abs(values[i] - before))} vs ${monthOnly(months[i - 1])}</span>`}`;
    },
  });
  const first = tracked[0], last = tracked.at(-1), change = last.v - first.v;
  $("#hist-change").textContent = tracked.length > 1 ? `${change >= 0 ? "+" : "−"}${money(Math.abs(change))} since ${monthOnly(months[first.i])}` : "";
  $("#hist-change").className = `hist-change ${change < 0 ? "down" : ""}`;
  $("#hist-note").textContent = tracked.length === 1
    ? `Tracked since ${shortDate(balances[account].start_date)} — the line grows as months pass.` : "Balance at the end of each month (today for the current month).";
}
$("#hist-prev").onclick = () => { historyYear--; renderHistory(); };
$("#hist-next").onclick = () => { historyYear++; renderHistory(); };

document.querySelectorAll(".account-row").forEach((row) => (row.onclick = () => {
  account = row.dataset.account;
  const b = balances[account];
  checkForm.reset();
  startForm.reset();
  fieldError(checkForm, "check", "");
  fieldError(startForm, "start", "");
  $("#balance-dialog").querySelectorAll(".currency").forEach((el) => (el.textContent = currencySymbol()));
  checkDate.set(isoDate(new Date()));
  if (b.start !== null) startForm.amount.value = inputAmount(b.start);
  startDate.set(b.start_date || isoDate(new Date()));
  $("#start-section").open = b.start === null;
  renderDialog();
  $("#balance-dialog").showModal();
  historyYear = new Date().getFullYear();
  if (b.start !== null) renderHistory();
  (b.start === null ? startForm : checkForm).amount.focus();
}));

const BALANCE_HINT = "Enter the balance as a number, like 1234,56. Use a minus for a negative balance: -250,00.";
checkForm.onsubmit = async (e) => {
  e.preventDefault();
  const amount = parseAmount(checkForm.amount.value);
  if (Number.isNaN(amount)) return fieldError(checkForm, "check", BALANCE_HINT);
  await api("/api/balance-checks", { method: "POST", body: { account, date: checkForm.date.value, amount } });
  checkForm.amount.value = "";
  await loadBalances();
  const result = balances[account].checks[0];
  toast(result.difference === null ? "Check saved" : result.difference === 0 ? "✓ The balance matches" : "The balance doesn't match");
};
checkForm.oninput = () => fieldError(checkForm, "check", "");

startForm.onsubmit = async (e) => {
  e.preventDefault();
  const amount = parseAmount(startForm.amount.value);
  if (Number.isNaN(amount)) return fieldError(startForm, "start", BALANCE_HINT);
  await api("/api/balance", { method: "PUT", body: { account, date: startForm.date.value, amount } });
  $("#start-section").open = false;
  toast("Starting point saved");
  await loadBalances();
  renderHistory();
  checkForm.amount.focus();
};
startForm.oninput = () => fieldError(startForm, "start", "");

$("#check-list").onclick = async (e) => {
  const btn = e.target.closest("[data-check]");
  if (!btn) return;
  await api(`/api/balance-checks/${btn.dataset.check}`, { method: "DELETE" });
  loadBalances();
};
