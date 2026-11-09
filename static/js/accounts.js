// Bank and savings balances: the account rows on the overview and the account dialog
// (expected balance, checks against the bank, starting point). Their history is on the History page.
import { datePicker } from "./controls.js";
import { currencySymbol, example, inputAmount, isoDate, money, parseAmount, shortDate } from "./format.js";
import { $, api, fieldError, once, toast } from "./ui.js";

const ACCOUNTS = { bank: "Bank account", savings: "Savings" };
const balances = {}; // per account: { start, start_date, expected, checks: [{ id, date, actual, expected, difference }] }
let account = "bank"; // the account open in the dialog
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
  $("#check-list").innerHTML = b.checks.map((c) => `
    <li class="${c.difference === null ? "" : c.difference === 0 ? "ok" : "off"}">
      <span class="check-date">${shortDate(c.date)}</span>
      <span class="check-actual">${money(c.actual)}</span>
      <span class="check-result">${c.difference === null ? "Before the starting point" : differenceText(c.difference)}</span>
      <button class="delete" data-check="${c.id}" aria-label="Remove this check">×</button>
    </li>`).join("");
}


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
  (b.start === null ? startForm : checkForm).amount.focus();
}));

const balanceHint = () => `Enter the balance as a number, like ${example("1234.56")}. Use a minus for a negative balance: ${example("-250.00")}.`;
checkForm.onsubmit = once(async (e) => {
  e.preventDefault();
  const amount = parseAmount(checkForm.amount.value);
  if (Number.isNaN(amount)) return fieldError(checkForm, "check", balanceHint());
  await api("/api/balance-checks", { method: "POST", body: { account, date: checkForm.date.value, amount } });
  checkForm.amount.value = "";
  await loadBalances();
  const result = balances[account].checks[0];
  toast(result.difference === null ? "Check saved" : result.difference === 0 ? "✓ The balance matches" : "The balance doesn't match");
});
checkForm.oninput = () => fieldError(checkForm, "check", "");

startForm.onsubmit = once(async (e) => {
  e.preventDefault();
  const amount = parseAmount(startForm.amount.value);
  if (Number.isNaN(amount)) return fieldError(startForm, "start", balanceHint());
  await api("/api/balance", { method: "PUT", body: { account, date: startForm.date.value, amount } });
  $("#start-section").open = false;
  toast("Starting point saved");
  await loadBalances();
  checkForm.amount.focus();
});
startForm.oninput = () => fieldError(startForm, "start", "");

$("#check-list").onclick = async (e) => {
  const btn = e.target.closest("[data-check]");
  if (!btn) return;
  await api(`/api/balance-checks/${btn.dataset.check}`, { method: "DELETE" });
  loadBalances();
};
