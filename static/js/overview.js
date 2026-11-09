// The overview page: the month's totals, whether it's ready for next month, the budget
// list and the transactions. All numbers come from GET /api/month; this only renders them.
import { loadBalances } from "./accounts.js";
import { openManager } from "./budget-editor.js";
import { menu, monthPicker } from "./controls.js";

let exportList = { shown: [], everything: true }; // what the Export menu offers (renderTransactions)
import { DATE_LOCALE, currentMonth, decimalComma, escapeHtml, isoDate, money, monthName, monthOnly, parseAmount, plural, shiftMonth, shortDate } from "./format.js";
import { isTransfer, lineBody, splitKey, state, uncategorized } from "./state.js";
import { openTransaction } from "./transaction.js";
import { $, api, confirmDialog, once, toast } from "./ui.js";

// Data per month, shared with the transaction dialog; cleared whenever data changes.
const monthCache = new Map();
export function monthData(ym, exclude = null) {
  const key = `${ym}:${exclude ?? ""}`;
  if (!monthCache.has(key)) monthCache.set(key, api(`/api/month?month=${ym}${exclude ? `&exclude=${exclude}` : ""}`));
  return monthCache.get(key);
}

export async function load() {
  $("#month-btn").textContent = monthName(state.month);
  $("#today-btn").hidden = state.month === currentMonth();
  monthCache.clear();
  [state.data, state.payees] = await Promise.all([monthData(state.month), api("/api/payees")]);
  state.allTransactions = state.search.allMonths ? await api("/api/transactions?month=") : null;
  render();
  renderResult();
  loadBalances();
  document.dispatchEvent(new Event("data-changed"));
}

export function setMonth(ym) {
  state.month = ym;
  state.selected.clear();
  load();
}

export function render() {
  renderTotals();
  renderBudgets();
  renderTransactions();
}

// ---- Top card: spent, budgets, and spending outside budgets ----
// A finished month gets a review of how it went instead.
function renderTotals() {
  const past = state.month < currentMonth();
  $("#total-label").textContent = past ? `${monthName(state.month)} in review` : `Spent in ${monthName(state.month)}`;
  ["#total-bar", "#total-sub"].forEach((s) => ($(s).hidden = false));
  $("#total-review").hidden = !past;
  if (past) return renderReview();
  const { spent, income, budget, outside, budget_spent: budgetSpent } = state.data.totals;
  const over = budgetSpent > budget;
  const leftOrOver = over ? `${money(budgetSpent - budget)} over` : `${money(budget - budgetSpent)} left`;
  $("#total").textContent = money(spent);
  $("#total-sub").textContent = outside ? `Budgets: ${money(budgetSpent)} of ${money(budget)} · ${leftOrOver}` : `of ${money(budget)} budgeted · ${leftOrOver}`;
  // Spending outside budgets comes on top of the budgets, so if the rest of the budgets is
  // spent too, the month ends `outside` over. Not spending it lowers that.
  const overall = spent - budget;
  const name = monthOnly(state.month, "long");
  const soFar = overall > 0 ? `so far it's ${money(overall)} more` : `so far you're still ${money(-overall)} under`;
  $("#total-over").hidden = !outside;
  $("#total-over").innerHTML = budget - budgetSpent > 0
    ? `<b>${money(outside)} spent outside your budgets.</b> If you use the rest of your budgets, ${name} costs that much more than budgeted; ${soFar}.`
    : `<b>${money(outside)} spent outside your budgets</b>, so ${name} costs ${money(Math.max(0, overall))} more than budgeted.`;
  $("#total-over").classList.toggle("warn", outside > 0);
  $("#total-income").hidden = !income;
  $("#total-income").textContent = `Income this month: ${money(income)}`;
  // Bar: spending within budgets, then outside them; the mark is where the total budget ends.
  const scale = Math.max(spent, budget) || 1;
  const bar = $("#total-bar");
  bar.querySelector(".in").style.width = `${(budgetSpent / scale) * 100}%`;
  bar.querySelector(".out").style.width = `${(outside / scale) * 100}%`;
  bar.querySelector(".budget-mark").style.left = `${(budget / scale) * 100}%`;
  bar.querySelector(".budget-mark").hidden = spent <= budget;
}

function renderReview() {
  const { spent, income, budget, outside, budget_spent: budgetSpent, carried_out: carried, net } = state.data.totals;
  const { unspent, saved } = state.data.leftover;
  const nextName = monthOnly(shiftMonth(state.month, 1), "long");
  $("#total").textContent = `${net < 0 ? "−" : "+"}${money(Math.abs(net))}`;
  $("#total-sub").textContent = net < 0 ? "More spent than earned" : "Left after income and spending";
  ["#total-bar", "#total-over", "#total-income"].forEach((s) => ($(s).hidden = true));
  const stat = (label, value, of = "") => `<div class="review-stat"><span class="label">${label}</span><b>${value}</b>${of ? `<span class="of">${of}</span>` : ""}</div>`;
  const over = state.data.groups.flatMap((g) => g.lines.filter((l) => l.budget !== null && l.spent > l.available).map((l) => l.name || g.name));
  const notes = [
    outside && `<b>${money(outside)}</b> spent outside your budgets`,
    over.length && `<b>${plural(over.length, "budget")}</b> went over: ${escapeHtml(over.join(", "))}`,
    (unspent || carried) && `<b>${money(unspent + carried)}</b> of your budgets wasn't used${carried ? `: ${money(carried)} carried over to ${nextName}` : ""}`,
    saved > 0 && `<b>${money(saved)}</b> moved to savings`,
    saved < 0 && `<b>${money(-saved)}</b> taken from savings`,
  ].filter(Boolean);
  $("#total-review").innerHTML = `
    <div class="review-stats">${stat("Income", money(income))}${stat("Spent", money(spent))}${stat("Budgets used", money(budgetSpent), `of ${money(budget)}`)}</div>
    ${notes.length ? `<ul class="review-notes">${notes.map((n) => `<li>${n}</li>`).join("")}</ul>` : ""}`;
}

// ---- "Ready for next month?" ----
function renderResult() {
  const o = state.data.outlook;
  const row = (label, value, cls = "", note = "") =>
    `<div class="result-row ${cls}"><span>${label}${note ? ` <span class="muted">${note}</span>` : ""}</span><span>${value}</span></div>`;
  const thisName = monthOnly(o.month, "long"), nextName = monthOnly(o.next, "long");
  $("#result-title").textContent = `Ready for ${nextName}?`;
  // Only for the month you're in, in its last week: earlier it's too early to say.
  $(".result-card").hidden = o.when !== "current" || o.too_early;
  if (o.balance === null) {
    $("#result-rows").innerHTML = `<p class="muted result-hint">Set up your bank account balance below to see whether you're ready for ${nextName}.</p>`;
    return;
  }
  const awaiting = o.expected_income > 0 || o.no_income_yet;
  const rows = [row(o.when === "past" ? `Bank balance on ${shortDate(o.end)}` : "Bank balance today", money(o.balance))];
  if (o.expected_income) rows.push(row("Income still expected", money(o.expected_income), "", `${thisName} · from your Outlook plans`));
  if (o.rest > 0) {
    const split = awaiting ? "can still be spent" : o.keep_for_next && o.saveable ? `${money(o.keep_for_next)} for ${nextName}, ${money(o.saveable)} for savings`
      : o.keep_for_next ? `all needed for ${nextName}` : "can go to savings";
    rows.push(row(`Unspent ${thisName} budget`, money(o.rest), "", `not carried over · ${split}`));
  }
  rows.push(row(`Needed on 1 ${nextName}`, money(o.needed), "strong",
    o.prepaid ? `${money(o.budget)} budget − ${money(o.prepaid)} already paid` : `${nextName} budget`));

  // The outcome: short (take from savings), only enough if the leftover isn't spent, or spare.
  // While this month's income is still to come it's a forecast, so there's nothing to move yet.
  const stillSpendable = o.when === "current" && o.short_if_spent > o.short;
  const orIfSpent = stillSpendable ? ` Or ${money(o.short_if_spent)} if you spend the rest of ${thisName}'s budget.` : "";
  let title, note = "", action = null;
  if (o.short > 0 && o.no_income_yet) {
    title = `${money(o.short)} short for ${nextName} so far`;
    note = `No income yet this month. Add your expected income in the Outlook to include it here.${orIfSpent}`;
  } else if (o.short > 0 && awaiting) {
    title = `Expecting ${money(o.short)} short for ${nextName}`;
    note = `You can take it from your savings once your income is in.${orIfSpent}`;
  } else if (o.short > 0) {
    title = `${money(o.short)} short for ${nextName}`;
    note = stillSpendable
      ? `Or ${money(o.short_if_spent)} if you spend the rest of ${thisName}'s budget. Move it from your savings.`
      : "Move this from your savings to cover next month's budget.";
    action = { kind: "withdraw", amount: stillSpendable ? o.short_if_spent : o.short, label: "Take from savings", cls: "primary-btn" };
  } else if (stillSpendable) {
    title = `Enough for ${nextName}, if you don't spend more`;
    note = `Spending the rest of ${thisName}'s budget would leave ${money(o.short_if_spent)} short. Unspent budget stays for ${nextName} instead of going to savings.`;
  } else if (awaiting) {
    title = `On track for ${nextName}`;
    note = "You'll have enough once your income is in.";
  } else if (o.spare > 0) {
    title = `${money(o.spare)} more than ${nextName} needs`;
    note = "You can move this to your savings.";
    action = { kind: "save", amount: o.spare, label: "Move to savings", cls: "ghost-btn" };
  } else {
    title = `Exactly enough for ${nextName}`;
  }
  rows.push(`<div class="result-gap ${o.short > 0 && !awaiting ? "short" : "ok"}">
    <div><b>${title}</b>${note ? `<span class="muted">${note}</span>` : ""}</div>
    ${action ? `<button class="${action.cls}" id="result-action">${action.label}</button>` : ""}
  </div>`);
  $("#result-rows").innerHTML = rows.join("");
  if (action) $("#result-action").onclick = () => openTransaction(null, action.kind, {
    amount: action.amount, date: o.when === "past" ? o.end : isoDate(new Date()),
    description: action.kind === "save" ? `Leftover ${monthName(o.month)}` : `For ${monthName(o.next)}`,
  });
}

// ---- Budget list ----
// Which categories are expanded (remembered per browser).
const expanded = new Set((() => {
  try { return JSON.parse(localStorage.getItem("budget.expanded") || "[]"); } catch { return []; }
})());
function saveExpanded() {
  try { localStorage.setItem("budget.expanded", JSON.stringify([...expanded])); } catch {}
}

// One compact row: a single budget line, or a category summing its items. Clicking it
// filters the transactions.
function budgetRow({ name, spent, avail, filterKey, label, level = 0, toggle = null, open = false, warn = false, line = null, carried = 0 }) {
  const over = spent > avail;
  const pct = avail ? Math.min(100, (spent / avail) * 100) : over ? 100 : 0;
  const details = [`${money(spent)} spent of ${money(avail)}`];
  if (line?.carried_in) details.push(`+${money(line.carried_in)} from ${monthOnly(shiftMonth(state.month, -1))}`);
  if (line?.extra) details.push(`+${money(line.extra)} income`);
  const next = monthOnly(shiftMonth(state.month, 1));
  const carry = !line || line.budget === null || over ? ""
    : `<button class="carry ${line.carry ? "on" : ""}" data-line="${line.key}" data-carry="${line.carry}"
        title="${line.carry ? `Leftover moves to ${next}. Click to keep it as savings.` : `Click to move this month's leftover to ${next}.`}">↪ ${line.carry ? next : "Carry"}</button>`;
  return `<div class="bl-row level-${level} ${over ? "over" : ""} ${state.filter?.key === filterKey ? "filtered" : ""}"
      data-filter="${filterKey}" data-label="${escapeHtml(label)}" title="${details.join(" · ")}">
    <span class="bl-toggle">${toggle !== null
      ? `<button class="chev ${open ? "open" : ""}" data-toggle="${toggle}" aria-label="${open ? "Collapse" : "Expand"} ${escapeHtml(name)}" aria-expanded="${open}"><svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>` : ""}</span>
    <span class="bl-name"><span class="bl-label">${escapeHtml(name)}</span>${warn ? `<span class="warn-dot" title="An item is over budget"></span>` : ""}${carried
      ? `<span class="carried-chip" title="${money(carried)} carried over from ${monthName(shiftMonth(state.month, -1))}">+${money(carried)}</span>` : ""}</span>
    <div class="bar"><span style="width:${pct}%"></span></div>
    <span class="bl-left">${over ? `${money(spent - avail)} over` : `${money(avail - spent)} left`}</span>
    <span class="bl-of muted">of ${money(avail)}</span>
    <span class="bl-carry">${carry}</span>
  </div>`;
}

function budgetGroup(group) {
  const { lines } = group;
  if (!group.has_items) {
    const l = lines[0];
    return `<div class="bl-group">${budgetRow({ name: group.name, spent: l.spent, avail: l.available, filterKey: l.key, label: group.name, line: l, carried: l.carried_in })}</div>`;
  }
  const open = expanded.has(group.id);
  const total = (f) => lines.reduce((sum, l) => sum + f(l), 0);
  const head = budgetRow({
    name: group.name, spent: total((l) => l.spent), avail: total((l) => l.available), filterKey: `k${group.id}`, label: group.name,
    toggle: group.id, open, warn: !open && lines.some((l) => l.spent > l.available), carried: total((l) => l.carried_in),
  });
  const rows = open ? lines.map((l) => budgetRow({
    name: l.name, spent: l.spent, avail: l.available, filterKey: l.key, label: `${group.name} · ${l.name}`, level: 1, line: l, carried: l.carried_in,
  })) : [];
  return `<div class="bl-group">${head}${rows.join("")}</div>`;
}

function renderBudgets() {
  const { groups, totals } = state.data;
  const rows = groups.map(budgetGroup);
  if (totals.outside > 0) {
    rows.push(`<div class="bl-group"><div class="bl-row level-0 uncat-row ${state.filter?.key === "u" ? "filtered" : ""}" data-filter="u" data-label="Uncategorized"
        title="Spent outside any budget">
      <span class="bl-toggle"></span><span class="bl-name">Uncategorized</span><span></span>
      <span class="bl-left">${money(totals.outside)}</span><span class="bl-of muted">spent</span><span></span>
    </div></div>`);
  }
  $("#carried-total").hidden = !totals.carried_in;
  $("#carried-total").textContent = `+${money(totals.carried_in)} carried over from ${monthOnly(shiftMonth(state.month, -1), "long")}`;
  const collapsible = groups.filter((g) => g.has_items);
  $("#expand-all").hidden = !collapsible.length;
  $("#expand-all").textContent = collapsible.every((g) => expanded.has(g.id)) ? "Collapse all" : "Expand all";
  $("#budgets").innerHTML = rows.length ? rows.join("")
    : `<div class="setup">
        <p>No budgets for ${monthName(state.month)} yet.</p>
        <button class="primary-btn" data-open-manager>Set up budgets</button>
      </div>`;
}

// Clicking a budget row filters the transactions; the arrow expands a category; the carry
// button toggles carry-over.
$("#budgets").onclick = async (e) => {
  if (e.target.closest("[data-open-manager]")) return openManager();
  const toggle = e.target.closest("[data-toggle]");
  if (toggle) {
    const id = Number(toggle.dataset.toggle);
    expanded.has(id) ? expanded.delete(id) : expanded.add(id);
    saveExpanded();
    return renderBudgets();
  }
  const carry = e.target.closest(".carry");
  if (carry) {
    await api("/api/rollover", { method: "PUT", body: { ...lineBody(carry.dataset.line), month: state.month, carry: carry.dataset.carry !== "true" } });
    return load();
  }
  const target = e.target.closest("[data-filter]");
  if (!target) return;
  state.filter = state.filter?.key === target.dataset.filter ? null : { key: target.dataset.filter, label: target.dataset.label };
  render();
  if (state.filter) $("#expenses").closest(".card").scrollIntoView({ behavior: "smooth", block: "start" });
};
$("#expand-all").onclick = () => {
  const ids = state.data.groups.filter((g) => g.has_items).map((g) => g.id);
  const all = ids.every((id) => expanded.has(id));
  ids.forEach((id) => (all ? expanded.delete(id) : expanded.add(id)));
  saveExpanded();
  renderBudgets();
};
$("#manage-btn").onclick = openManager;

// ---- Transactions ----
function matchesFilter(t) {
  const { filter } = state;
  if (!filter) return true;
  if (filter.key === "u") return t.kind === "expense" && uncategorized(t) > 0;
  if (filter.key[0] === "k") return t.splits.some((s) => `k${s.category_id}` === filter.key);
  return t.splits.some((s) => splitKey(s) === filter.key);
}

function matchesSearch(t) {
  const { query, type } = state.search;
  if (type !== "all" && (isTransfer(t) ? "transfer" : t.kind) !== type) return false;
  // Every word must match: text in the payee, note or budget names, or an amount.
  const text = [t.payee, t.description, ...t.splits.flatMap((s) => [s.category, s.item]),
    isTransfer(t) ? "savings" : "", uncategorized(t) > 0 && t.kind === "expense" ? "uncategorized" : ""]
    .filter(Boolean).join(" ").toLowerCase();
  return query.toLowerCase().split(/\s+/).filter(Boolean).every((word) => {
    const amount = parseAmount(word);
    if (!Number.isNaN(amount) && /\d/.test(word)) return [t.amount, ...t.splits.map((s) => s.amount)].includes(amount) || text.includes(word);
    return text.includes(word);
  });
}

// Spending of the day, plus any income received.
function dayTotal(list) {
  const total = (kind) => list.filter((t) => t.kind === kind).reduce((sum, t) => sum + t.amount, 0);
  const spent = total("expense"), received = total("income");
  return [spent ? money(spent) : "", received ? `+ ${money(received)}` : ""].filter(Boolean).join(" · ");
}

function dayLabel(iso) {
  const now = new Date();
  if (iso === isoDate(now)) return "Today";
  if (iso === isoDate(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1))) return "Yesterday";
  const d = new Date(iso + "T00:00");
  return d.toLocaleDateString(DATE_LOCALE, { weekday: "long", day: "numeric", month: "long", ...(d.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }) });
}

function transactionRow(t) {
  const check = state.selecting ? `<span class="check" aria-hidden="true"></span>` : "";
  const selected = state.selected.has(t.id) ? "selected" : "";
  if (isTransfer(t)) {
    return `<li class="expense transfer ${selected}" data-id="${t.id}" tabindex="0">${check}
      <div class="what">
        <span class="title">${t.kind === "save" ? "Moved to savings" : "Taken from savings"}</span>
        ${t.description ? `<span class="details muted">${escapeHtml(t.description)}</span>` : ""}
      </div>
      <span class="amount">${t.kind === "save" ? "→" : "←"} ${money(t.amount)}</span>
    </li>`;
  }
  // Title: who was paid (or who paid); details: the note and which budget(s) it came from or went to.
  const income = t.kind === "income";
  const rest = uncategorized(t);
  const parts = t.splits.map((s) => escapeHtml(s.item || s.category) + (t.splits.length > 1 || rest ? ` ${money(s.amount)}` : ""));
  if (income && parts.length) parts[0] = `Added to ${parts[0]}`;
  if (rest > 0) parts.push(`<span class="uncat">${income ? "Income" : "Uncategorized"}${t.splits.length ? ` ${money(rest)}` : ""}</span>`);
  const details = [t.payee && t.description ? escapeHtml(t.description) : "", parts.join(" + "),
    t.paid_date ? `paid ${shortDate(t.paid_date)}` : ""].filter(Boolean);
  return `<li class="expense ${income ? "income" : ""} ${selected}" data-id="${t.id}" tabindex="0">${check}
    <div class="what">
      <span class="title">${escapeHtml(t.payee || t.description || "Expense")}</span>
      <span class="details muted">${details.join(" · ")}</span>
    </div>
    <span class="amount">${income ? "+ " : ""}${money(t.amount)}</span>
  </li>`;
}

function renderTransactions() {
  // This month's transactions (or every month's, when searching all months), narrowed by
  // the budget filter, the type filter and the search box.
  const { search, filter, selecting, selected } = state;
  const decimal = decimalComma() ? "," : ".";
  const monthly = state.data.transactions;
  const searching = search.query || search.type !== "all";
  const source = search.allMonths && searching && state.allTransactions ? state.allTransactions : monthly;
  const shown = source.filter((t) => matchesFilter(t) && matchesSearch(t));
  $("#filter").hidden = !filter;
  if (filter) $("#filter").innerHTML = `${escapeHtml(filter.label)} <button class="clear-filter" aria-label="Show all spending">×</button>`;
  $("#count").textContent = filter || searching ? `${shown.length} of ${source.length}` : monthly.length ? plural(monthly.length, "transaction") : "";
  $("#select-btn").hidden = selecting || !shown.length;
  // Export: what the list shows, or every transaction (a menu, see below). While selecting,
  // the selection bar's Export takes its place, for the selected ones.
  $("#csv-btn").hidden = selecting || !shown.length;
  exportList = { shown, everything: shown.length === monthly.length && source === monthly };
  $("#selection-bar").hidden = !selecting;
  $("#selection-count").textContent = selected.size ? `${selected.size} selected` : "Select transactions to export or delete";
  $("#select-delete").disabled = !selected.size;
  $("#select-all").hidden = shown.every((t) => selected.has(t.id));
  $("#select-export").classList.toggle("disabled", !selected.size);
  $("#select-export").setAttribute("aria-disabled", String(!selected.size));
  $("#select-export").href = `/api/transactions-csv?ids=${[...selected].join(",")}&decimal=${decimal}`;
  $("#empty").hidden = shown.length > 0;
  const where = source === monthly ? monthName(state.month) : "any month";
  $("#empty").textContent = search.query ? `No transactions matching “${search.query}” in ${where}.`
    : filter || searching ? `No matching transactions in ${where}.` : "Nothing recorded this month yet.";

  const days = {};
  for (const t of shown) (days[t.date] ||= []).push(t);
  $("#expenses").classList.toggle("selecting", selecting);
  $("#expenses").innerHTML = Object.entries(days).map(([day, list]) => `
    <li class="day">
      <div class="day-head"><span>${dayLabel(day)}</span><span>${dayTotal(list)}</span></div>
      <ul>${list.map(transactionRow).join("")}</ul>
    </li>`).join("");
}

$("#filter").onclick = (e) => {
  if (!e.target.closest(".clear-filter")) return;
  state.filter = null;
  render();
};

// Search and type filter
async function searchChanged() {
  if (state.search.allMonths && !state.allTransactions) state.allTransactions = await api("/api/transactions?month=");
  renderTransactions();
}
$("#search").oninput = (e) => {
  state.search.query = e.target.value.trim();
  searchChanged();
};
$("#type-filter").onclick = (e) => {
  if (!e.target.dataset.type) return;
  state.search.type = e.target.dataset.type;
  document.querySelectorAll("#type-filter button").forEach((b) => b.classList.toggle("active", b === e.target));
  searchChanged();
};
$("#all-months").onchange = (e) => {
  state.search.allMonths = e.target.checked;
  searchChanged(); // also points the export at every month, or this one
};

// Click a transaction to edit it, or select several to delete.
$("#expenses").onclick = (e) => {
  const row = e.target.closest(".expense");
  if (!row) return;
  const id = Number(row.dataset.id);
  if (state.selecting) {
    state.selected.has(id) ? state.selected.delete(id) : state.selected.add(id);
    return renderTransactions();
  }
  openTransaction([...state.data.transactions, ...(state.allTransactions || [])].find((t) => t.id === id));
};
$("#expenses").onkeydown = (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    e.target.closest(".expense")?.click();
  }
};
$("#select-btn").onclick = () => {
  state.selecting = true;
  renderTransactions();
};
// Export: the transactions in the list, or all of them, as CSV with the decimal separator in use.
menu($("#csv-btn"), () => {
  const decimal = decimalComma() ? "," : ".";
  const { shown, everything } = exportList;
  const list = everything ? `month=${state.month}` : `ids=${shown.map((t) => t.id).join(",")}`;
  return `<a class="opt" download href="/api/transactions-csv?${list}&decimal=${decimal}">
      ${everything ? `${monthName(state.month)}` : "The transactions shown"} <span class="muted">· ${plural(shown.length, "transaction")}</span></a>
    <a class="opt" download href="/api/transactions-csv?month=&decimal=${decimal}">All transactions <span class="muted">· every month</span></a>`;
});

// Every transaction shown (with the search and filters), ready to export or delete.
$("#select-all").onclick = () => {
  const { search } = state;
  const searching = search.query || search.type !== "all";
  const source = search.allMonths && searching && state.allTransactions ? state.allTransactions : state.data.transactions;
  source.filter((t) => matchesFilter(t) && matchesSearch(t)).forEach((t) => state.selected.add(t.id));
  renderTransactions();
};
$("#select-export").onclick = (e) => {
  if (!state.selected.size) e.preventDefault();
};
$("#select-cancel").onclick = () => {
  state.selecting = false;
  state.selected.clear();
  renderTransactions();
};
$("#select-delete").onclick = once(async () => {
  const what = plural(state.selected.size, "transaction");
  if (!(await confirmDialog({
    title: `Delete ${what}?`, message: "They're removed for good. Your budgets and balances update right away.",
    confirm: `Delete ${what}`, danger: true,
  }))) return;
  await api("/api/transactions-delete", { method: "POST", body: { ids: [...state.selected] } });
  state.selecting = false;
  state.selected.clear();
  toast(`Deleted ${what}`);
  load();
});

// ---- Month navigation ----
$("#prev-month").onclick = () => setMonth(shiftMonth(state.month, -1));
$("#next-month").onclick = () => setMonth(shiftMonth(state.month, 1));
$("#today-btn").onclick = () => setMonth(currentMonth());
monthPicker($("#month-btn"), { get: () => state.month, set: setMonth });
