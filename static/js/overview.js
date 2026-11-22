// The overview page: the month's totals, whether it's ready for next month, the budget
// list and the transactions. All numbers come from GET /api/month; this only renders them.
import { loadBalances } from "./accounts.js";
import { openManager } from "./budget-editor.js";
import { menu, monthPicker } from "./controls.js";

let exportList = { shown: [], everything: true }; // what the Export menu offers (renderTransactions)
import { DATE_LOCALE, cap, currentMonth, decimalComma, escapeHtml, isoDate, money, monthName, monthOnly, parseAmount, shiftMonth, shortDate } from "./format.js";
import { helpTip } from "./help.js";
import { t } from "./i18n.js";

const T = t; // where `t` is a transaction
import { isSimple, isTransfer, lineBody, splitKey, state, uncategorized } from "./state.js";
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
  $("#month-btn").textContent = cap(monthName(state.month));
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
  $("#total-label").textContent = past ? cap(t("overview.inReview", { month: monthName(state.month) })) : t("overview.spentIn", { month: monthName(state.month) });
  ["#total-bar", "#total-sub"].forEach((s) => ($(s).hidden = false));
  $("#total-review").hidden = !past;
  if (past) return renderReview();
  const { spent, income, budget, outside, budget_spent: budgetSpent } = state.data.totals;
  const over = budgetSpent > budget;
  const leftOrOver = over ? t("common.over", { amount: money(budgetSpent - budget) }) : t("common.left", { amount: money(budget - budgetSpent) });
  $("#total").textContent = money(spent);
  $("#total-sub").textContent = outside
    ? t("overview.budgetsOf", { spent: money(budgetSpent), budget: money(budget), left: leftOrOver })
    : t("overview.ofBudgeted", { budget: money(budget), left: leftOrOver });
  // Spending outside budgets comes on top of the budgets, so if the rest of the budgets is
  // spent too, the month ends `outside` over. Not spending it lowers that.
  const overall = spent - budget;
  const name = monthOnly(state.month, "long");
  const soFar = overall > 0 ? t("overview.soFarItsMore", { amount: money(overall) }) : t("overview.soFarYoureStillUnder", { amount: money(-overall) });
  $("#total-over").hidden = !outside;
  $("#total-over").innerHTML = budget - budgetSpent > 0
    ? t("overview.outsideBudgetsSoFar", { amount: money(outside), month: name, so_far: soFar })
    : t("overview.outsideBudgetsOver", { amount: money(outside), month: name, more: money(Math.max(0, overall)) });
  $("#total-over").classList.toggle("warn", outside > 0);
  $("#total-income").hidden = !income;
  $("#total-income").textContent = t("overview.incomeThisMonth", { amount: money(income) });
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
  $("#total-sub").textContent = net < 0 ? t("common.moreSpentThanEarned") : t("common.leftAfterIncomeAndSpending");
  ["#total-bar", "#total-over", "#total-income"].forEach((s) => ($(s).hidden = true));
  const stat = (label, value, of = "") => `<div class="review-stat"><span class="label">${label}</span><b>${value}</b>${of ? `<span class="of">${of}</span>` : ""}</div>`;
  const over = state.data.groups.flatMap((g) => g.lines.filter((l) => l.budget !== null && l.spent > l.available).map((l) => l.name || g.name));
  const notes = [
    outside && t("overview.spentOutsideYourBudgets", { amount: money(outside) }),
    over.length && t("overview.reviewOverBudget", { count: over.length, names: escapeHtml(over.join(", ")) }),
    (unspent || carried) && (carried
      ? t("overview.reviewUnusedCarried", { amount: money(unspent + carried), carried: money(carried), month: nextName })
      : t("overview.reviewUnused", { amount: money(unspent + carried) })),
    saved > 0 && t("overview.movedToSavings", { amount: money(saved) }),
    saved < 0 && t("overview.takenFromSavings", { amount: money(-saved) }),
  ].filter(Boolean);
  $("#total-review").innerHTML = `
    <div class="review-stats">${stat(t("common.income"), money(income))}${stat(t("common.spent"), money(spent))}${stat(t("overview.budgetsUsed"), money(budgetSpent), t("common.of", { amount: money(budget) }))}</div>
    ${notes.length ? `<ul class="review-notes">${notes.map((n) => `<li>${n}</li>`).join("")}</ul>` : ""}`;
}

// ---- "Ready for next month?" ----
function renderResult() {
  const o = state.data.outlook;
  const row = (label, value, cls = "", note = "") =>
    `<div class="result-row ${cls}"><span>${label}${note ? ` <span class="muted">${note}</span>` : ""}</span><span>${value}</span></div>`;
  const thisName = monthOnly(o.month, "long"), nextName = monthOnly(o.next, "long");
  $("#result-title").innerHTML = `${t("overview.readyFor", { month: nextName })} ${helpTip("ready")}`;
  // Only for the month you're in, in its last week: earlier it's too early to say. It counts on
  // the income planned in the Outlook, so it's one of the features beyond the basics.
  $(".result-card").hidden = o.when !== "current" || o.too_early || isSimple();
  if (o.balance === null) {
    $("#result-rows").innerHTML = `<p class="muted result-hint">${t("overview.setUpYourBankAccount", { month: nextName })}</p>`;
    return;
  }
  const awaiting = o.expected_income > 0 || o.no_income_yet;
  const rows = [row(o.when === "past" ? t("overview.bankBalanceOn", { date: shortDate(o.end) }) : t("overview.bankBalanceToday"), money(o.balance))];
  if (o.expected_income) rows.push(row(t("overview.incomeStillExpected"), money(o.expected_income), "", t("overview.fromYourOutlookPlans", { month: thisName })));
  if (o.rest > 0) {
    const split = awaiting ? t("overview.canStillBeSpent")
      : o.keep_for_next && o.saveable ? t("overview.forForSavings", { next: money(o.keep_for_next), month: nextName, saveable: money(o.saveable) })
      : o.keep_for_next ? t("overview.allNeededFor", { month: nextName }) : t("overview.canGoToSavings");
    rows.push(row(t("overview.unspentBudget", { month: thisName }), money(o.rest), "", t("overview.notCarriedOver", { split })));
  }
  rows.push(row(t("overview.neededOn", { month: nextName }), money(o.needed), "strong",
    o.prepaid ? t("overview.budgetAlreadyPaid", { budget: money(o.budget), paid: money(o.prepaid) }) : t("overview.budget", { month: nextName })));

  // The outcome: short (take from savings), only enough if the leftover isn't spent, or spare.
  // While this month's income is still to come it's a forecast, so there's nothing to move yet.
  const stillSpendable = o.when === "current" && o.short_if_spent > o.short;
  const orIfSpent = stillSpendable ? ` ${t("overview.orIfYouSpendThe", { amount: money(o.short_if_spent), month: thisName })}` : "";
  let title, note = "", action = null;
  if (o.short > 0 && o.no_income_yet) {
    title = t("overview.shortForSoFar", { amount: money(o.short), month: nextName });
    note = t("overview.noIncomeYetThisMonth") + orIfSpent;
  } else if (o.short > 0 && awaiting) {
    title = t("overview.expectingShortFor", { amount: money(o.short), month: nextName });
    note = t("common.youCanTakeItFrom") + orIfSpent;
  } else if (o.short > 0) {
    title = t("overview.shortFor", { amount: money(o.short), month: nextName });
    note = stillSpendable
      ? `${t("overview.orIfYouSpendThe", { amount: money(o.short_if_spent), month: thisName })} ${t("overview.moveItFromYourSavings")}`
      : t("overview.moveThisFromYourSavings");
    action = { kind: "withdraw", amount: stillSpendable ? o.short_if_spent : o.short, label: t("common.takeFromSavings"), cls: "primary-btn" };
  } else if (stillSpendable) {
    title = t("overview.enoughForIfYouDont", { month: nextName });
    note = t("overview.spendingTheRestOfS", { month: thisName, amount: money(o.short_if_spent), next: nextName });
  } else if (awaiting) {
    title = t("overview.onTrackFor", { month: nextName });
    note = t("overview.youllHaveEnoughOnceYour");
  } else if (o.spare > 0) {
    title = t("overview.moreThanNeeds", { amount: money(o.spare), month: nextName });
    note = t("overview.youCanMoveThisTo");
    action = { kind: "save", amount: o.spare, label: t("overview.moveToSavings"), cls: "ghost-btn" };
  } else {
    title = t("overview.exactlyEnoughFor", { month: nextName });
  }
  rows.push(`<div class="result-gap ${o.short > 0 && !awaiting ? "short" : "ok"}">
    <div><b>${title}</b>${note ? `<span class="muted">${note}</span>` : ""}</div>
    ${action ? `<button class="${action.cls}" id="result-action">${action.label}</button>` : ""}
  </div>`);
  $("#result-rows").innerHTML = rows.join("");
  if (action) $("#result-action").onclick = () => openTransaction(null, action.kind, {
    amount: action.amount, date: o.when === "past" ? o.end : isoDate(new Date()),
    description: action.kind === "save" ? t("overview.leftover", { month: monthName(o.month) }) : t("common.for", { month: monthName(o.next) }),
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
  const details = [t("common.spentOf", { spent: money(spent), budget: money(avail) })];
  if (line?.carried_in) details.push(t("overview.from", { amount: money(line.carried_in), month: monthOnly(shiftMonth(state.month, -1)) }));
  if (line?.extra) details.push(t("overview.income", { amount: money(line.extra) }));
  const next = monthOnly(shiftMonth(state.month, 1));
  // Carrying over is one of the features beyond the basics: only shown with every feature on.
  const carryTip = line?.carry ? t("overview.whatsLeftMovesToClick", { month: next }) : t("overview.clickToMoveWhatsLeft", { month: next });
  const carry = !line || line.budget === null || over || isSimple() ? ""
    : `<button class="carry ${line.carry ? "on" : ""}" data-line="${line.key}" data-carry="${line.carry}" title="${carryTip}" aria-label="${carryTip}">↪ ${line.carry ? cap(next) : `<span class="carry-word">${t("overview.carryShort")}</span>`}</button>`;
  return `<div class="bl-row level-${level} ${over ? "over" : ""} ${state.filter?.key === filterKey ? "filtered" : ""}"
      data-filter="${filterKey}" data-label="${escapeHtml(label)}" title="${details.join(" · ")}">
    <span class="bl-toggle">${toggle !== null
      ? `<button class="chev ${open ? "open" : ""}" data-toggle="${toggle}" aria-label="${open ? t("overview.collapse", { name: escapeHtml(name) }) : t("overview.expand", { name: escapeHtml(name) })}" aria-expanded="${open}"><svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>` : ""}</span>
    <span class="bl-name"><span class="bl-label">${escapeHtml(name)}</span>${warn ? `<span class="warn-dot" title="${t("overview.anItemIsOverBudget")}"></span>` : ""}${carried
      ? `<span class="carried-chip" title="${t("overview.carriedOverFrom", { amount: money(carried), month: monthName(shiftMonth(state.month, -1)) })}">+${money(carried)}</span>` : ""}</span>
    <div class="bar"><span style="width:${pct}%"></span></div>
    <span class="bl-left">${over ? t("common.over", { amount: money(spent - avail) }) : t("common.left", { amount: money(avail - spent) })}</span>
    <span class="bl-of muted">${t("common.of", { amount: money(avail) })}</span>
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
    rows.push(`<div class="bl-group"><div class="bl-row level-0 uncat-row ${state.filter?.key === "u" ? "filtered" : ""}" data-filter="u" data-label="${t("common.noBudget")}"
        title="${t("overview.spentOutsideAnyBudget")}">
      <span class="bl-toggle"></span><span class="bl-name">${t("common.noBudget")} ${helpTip("no-budget")}</span><span></span>
      <span class="bl-left">${money(totals.outside)}</span><span class="bl-of muted">${t("overview.spent")}</span><span></span>
    </div></div>`);
  }
  $("#carried-total").hidden = !totals.carried_in;
  $("#carried-total").textContent = t("overview.carriedTotal", { amount: money(totals.carried_in), month: monthOnly(shiftMonth(state.month, -1), "long") });
  const collapsible = groups.filter((g) => g.has_items);
  $("#expand-all").hidden = !collapsible.length;
  $("#expand-all").textContent = collapsible.every((g) => expanded.has(g.id)) ? t("overview.collapseAll") : t("overview.expandAll");
  $("#budgets").innerHTML = rows.length ? rows.join("")
    : `<div class="setup">
        <p>${t("overview.noBudgetsForYet", { month: monthName(state.month) })}</p>
        <button class="primary-btn" data-open-manager>${t("common.setUpBudgets")}</button>
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
    isTransfer(t) ? T("overview.savings") : "", uncategorized(t) > 0 && t.kind === "expense" ? T("common.noBudget") : ""]
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
  if (iso === isoDate(now)) return t("common.today");
  if (iso === isoDate(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1))) return t("overview.yesterday");
  const d = new Date(iso + "T00:00");
  return cap(d.toLocaleDateString(DATE_LOCALE, { weekday: "long", day: "numeric", month: "long", ...(d.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }) }));
}

function transactionRow(t) {
  const check = state.selecting ? `<span class="check" aria-hidden="true"></span>` : "";
  const selected = state.selected.has(t.id) ? "selected" : "";
  if (isTransfer(t)) {
    return `<li class="expense transfer ${selected}" data-id="${t.id}" tabindex="0">${check}
      <div class="what">
        <span class="title">${t.kind === "save" ? T("overview.transferToSavings") : T("overview.transferFromSavings")}</span>
        ${t.description ? `<span class="details muted">${escapeHtml(t.description)}</span>` : ""}
      </div>
      <span class="amount">${t.kind === "save" ? "→" : "←"} ${money(t.amount)}</span>
    </li>`;
  }
  // Title: who was paid (or who paid); details: the note and which budget(s) it came from or went to.
  const income = t.kind === "income";
  const rest = uncategorized(t);
  const parts = t.splits.map((s) => escapeHtml(s.item || s.category) + (t.splits.length > 1 || rest ? ` ${money(s.amount)}` : ""));
  if (income && parts.length) parts[0] = T("overview.addedTo", { budget: parts[0] });
  if (rest > 0) parts.push(`<span class="uncat">${income ? T("common.income") : T("common.noBudget")}${t.splits.length ? ` ${money(rest)}` : ""}</span>`);
  const details = [t.payee && t.description ? escapeHtml(t.description) : "", parts.join(" + "),
    t.paid_date ? T("overview.paid", { date: shortDate(t.paid_date) }) : ""].filter(Boolean);
  return `<li class="expense ${income ? "income" : ""} ${selected}" data-id="${t.id}" tabindex="0">${check}
    <div class="what">
      <span class="title">${escapeHtml(t.payee || t.description || T("common.expense"))}</span>
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
  if (filter) $("#filter").innerHTML = `${escapeHtml(filter.label)} <button class="clear-filter" aria-label="${t("overview.showAllSpending")}">×</button>`;
  $("#count").textContent = filter || searching ? t("overview.of", { shown: shown.length, total: source.length })
    : monthly.length ? t("common.transactionCount", { count: monthly.length }) : "";
  $("#select-btn").hidden = selecting || !shown.length;
  // Export: what the list shows, or every transaction (a menu, see below). While selecting,
  // the selection bar's Export takes its place, for the selected ones.
  $("#csv-btn").hidden = selecting || !shown.length;
  exportList = { shown, everything: shown.length === monthly.length && source === monthly };
  $("#selection-bar").hidden = !selecting;
  $("#selection-count").textContent = selected.size ? t("overview.selected", { n: selected.size }) : t("overview.selectTransactionsToExportOr");
  $("#select-delete").disabled = !selected.size;
  $("#select-all").hidden = shown.every((t) => selected.has(t.id));
  $("#select-export").classList.toggle("disabled", !selected.size);
  $("#select-export").setAttribute("aria-disabled", String(!selected.size));
  $("#select-export").href = `/api/transactions-csv?ids=${[...selected].join(",")}&decimal=${decimal}`;
  $("#empty").hidden = shown.length > 0;
  const where = source === monthly ? monthName(state.month) : t("overview.anyMonth");
  $("#empty").textContent = search.query ? t("overview.noTransactionsMatchingIn", { query: search.query, where })
    : filter || searching ? t("overview.noMatchingTransactionsIn", { where }) : t("overview.nothingRecordedThisMonthYet");

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
      ${everything ? cap(monthName(state.month)) : t("overview.theTransactionsShown")} <span class="muted">· ${t("common.transactionCount", { count: shown.length })}</span></a>
    <a class="opt" download href="/api/transactions-csv?month=&decimal=${decimal}">${t("overview.allTransactions")} <span class="muted">· ${t("overview.everyMonth")}</span></a>`;
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
  const n = state.selected.size;
  if (!(await confirmDialog({
    title: t("overview.deleteSelectedTitle", { count: n }), message: t("overview.theyreRemovedForGoodYour"),
    confirm: t("overview.deleteSelectedButton", { count: n }), danger: true,
  }))) return;
  await api("/api/transactions-delete", { method: "POST", body: { ids: [...state.selected] } });
  state.selecting = false;
  state.selected.clear();
  toast(t("overview.deletedSelected", { count: n }));
  load();
});

// ---- Month navigation ----
$("#prev-month").onclick = () => setMonth(shiftMonth(state.month, -1));
$("#next-month").onclick = () => setMonth(shiftMonth(state.month, 1));
$("#today-btn").onclick = () => setMonth(currentMonth());
monthPicker($("#month-btn"), { get: () => state.month, set: setMonth });
