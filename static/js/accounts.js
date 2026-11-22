// Bank and savings balances: the account rows on the overview and the account dialog
// (expected balance, checks against the bank, starting point). Their history is on the History page.
import { datePicker } from "./controls.js";
import { currencySymbol, example, inputAmount, isoDate, money, parseAmount, shortDate } from "./format.js";
import { html, setHtml } from "./html.js";
import { t } from "./i18n.js";
import { isSimple } from "./state.js";
import { $, api, fieldError, once, toast } from "./ui.js";

const ACCOUNTS = { bank: t("common.bankAccount"), savings: t("common.savings") };
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
  if (diff === 0) return t("accounts.matches");
  return diff < 0
    ? t("accounts.lessInYourBankA", { amount: money(-diff) })
    : t("accounts.moreInYourBankA", { amount: money(diff) });
}

function renderRows() {
  for (const [a, b] of Object.entries(balances)) {
    const row = $(`.account-row[data-account="${a}"]`);
    const set = b.start !== null;
    const last = b.checks.find((c) => c.difference !== null);
    // In Simple mode an account appears once it's tracked (see the bank and savings offers).
    row.hidden = !set && isSimple();
    row.querySelector(".balance-amount").textContent = b.expected !== null ? money(b.expected) : set ? "—" : t("accounts.notSetUp");
    const status = row.querySelector(".balance-status");
    status.classList.remove("ok", "off");
    if (!set) status.textContent = t("accounts.addAStartingBalanceTo");
    else if (!last) status.textContent = t("accounts.expectedTodayNotCheckedWith");
    else if (last.difference === 0) {
      status.textContent = t("accounts.matchedYourBankOn", { date: shortDate(last.date) });
      status.classList.add("ok");
    } else {
      status.textContent = t("accounts.offOn", { amount: money(Math.abs(last.difference)), date: shortDate(last.date) });
      status.classList.add("off");
    }
    row.querySelector(".balance-action").textContent = set ? t("common.check") : t("accounts.setUp");
  }
  $(".accounts").hidden = [...document.querySelectorAll(".account-row")].every((row) => row.hidden);
  if ($("#balance-dialog").open) renderDialog();
}

function renderDialog() {
  const b = balances[account];
  const set = b.start !== null;
  $("#balance-title").textContent = ACCOUNTS[account];
  setHtml($("#balance-summary"), set
    ? html`<span class="label">${t("accounts.expectedToday")}</span>
       <span class="balance-amount">${b.expected !== null ? money(b.expected) : "—"}</span>
       <span class="muted">${account === "bank"
         ? t("accounts.howBankIsCounted", { amount: money(b.start), date: shortDate(b.start_date) })
         : t("accounts.howSavingsAreCounted", { amount: money(b.start), date: shortDate(b.start_date) })}</span>`
    : html`<span class="muted">${t("accounts.firstEnterAStartingBalance")}</span>`);
  checkForm.hidden = !set;
  setHtml($("#check-list"), html`${b.checks.map((c) => html`
    <li class="${c.difference === null ? "" : c.difference === 0 ? "ok" : "off"}">
      <span class="check-date">${shortDate(c.date)}</span>
      <span class="check-actual">${money(c.actual)}</span>
      <span class="check-result">${c.difference === null ? t("accounts.beforeTheStartingBalance") : differenceText(c.difference)}</span>
      <button class="delete" data-check="${c.id}" aria-label="${t("accounts.removeThisCheck")}">×</button>
    </li>`)}`);
}


// Opens the dialog of an account ("bank" or "savings"), also from elsewhere (the savings offer).
export function openAccount(name) {
  account = name;
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
}
document.querySelectorAll(".account-row").forEach((row) => (row.onclick = () => openAccount(row.dataset.account)));

const balanceHint = () => t("accounts.enterTheBalanceAsA", { example: example("1234.56"), negative: example("-250.00") });
checkForm.onsubmit = once(async (e) => {
  e.preventDefault();
  const amount = parseAmount(checkForm.amount.value);
  if (Number.isNaN(amount)) return fieldError(checkForm, "check", balanceHint());
  await api("/api/balance-checks", { method: "POST", body: { account, date: checkForm.date.value, amount } });
  checkForm.amount.value = "";
  await loadBalances();
  const result = balances[account].checks[0];
  toast(result.difference === null ? t("accounts.checkSaved") : result.difference === 0 ? t("accounts.theBalanceMatches") : t("accounts.theBalanceDoesntMatch"));
});
checkForm.oninput = () => fieldError(checkForm, "check", "");

startForm.onsubmit = once(async (e) => {
  e.preventDefault();
  const amount = parseAmount(startForm.amount.value);
  if (Number.isNaN(amount)) return fieldError(startForm, "start", balanceHint());
  await api("/api/balance", { method: "PUT", body: { account, date: startForm.date.value, amount } });
  $("#start-section").open = false;
  toast(t("accounts.startingBalanceSaved"));
  await loadBalances();
  document.dispatchEvent(new Event("data-changed")); // e.g. the getting-started guide
  checkForm.amount.focus();
});
startForm.oninput = () => fieldError(startForm, "start", "");

$("#check-list").onclick = async (e) => {
  const btn = e.target.closest("[data-check]");
  if (!btn) return;
  await api(`/api/balance-checks/${btn.dataset.check}`, { method: "DELETE" });
  loadBalances();
};
