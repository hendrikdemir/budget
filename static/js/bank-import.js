// Importing transactions from a bank export (CSV). The server reads the file and suggests
// payees, budgets and likely duplicates; here every transaction is reviewed before any is added.
import { combobox } from "./controls.js";
import { DATE_LOCALE, cap, escapeHtml, money, shortDate } from "./format.js";
import { t as T } from "./i18n.js";
import { load } from "./overview.js";
import { $, api, once, toast } from "./ui.js";

const KINDS = { expense: T("common.expense"), income: T("common.income"), save: T("common.toSavings"), withdraw: T("common.fromSavings") };
let rows = []; // [{ t, include, budget (combobox) }]

$("#bank-import-btn").onclick = () => $("#bank-file").click();
$("#bank-file").onchange = async (e) => {
  const file = e.target.files[0];
  e.target.value = ""; // so the same file can be chosen again
  if (!file) return;
  const preview = await api("/api/bank-import-preview", { method: "POST", body: await file.arrayBuffer() });
  open(preview);
};

const weekday = (iso) => cap(new Date(`${iso}T00:00`).toLocaleDateString(DATE_LOCALE, { weekday: "short" }));

function open({ bank, transactions, lines }) {
  const duplicates = transactions.filter((t) => t.duplicate).length;
  $("#bank-title").textContent = T("import.title", { count: transactions.length, bank });
  $("#bank-hint").textContent = T("import.checkEachOneAndChoose") +
    (duplicates ? ` ${T("import.duplicates", { count: duplicates })}` : "");
  $("#bank-list").innerHTML = transactions.map((t, i) => {
    const transfer = t.kind === "save" || t.kind === "withdraw";
    const sign = t.kind === "income" || t.kind === "withdraw" ? "+ " : "";
    return `<li class="bank-row" data-i="${i}">
      <label class="bank-include" aria-label="${T("import.addThisTransaction")}"><input type="checkbox" ${t.duplicate ? "" : "checked"}></label>
      <div class="bank-main">
        <div class="bank-top">
          <span>${weekday(t.date)} ${shortDate(t.date)}${t.paid_date ? ` <span class="muted">· ${T("import.leftYourBank", { date: shortDate(t.paid_date) })}</span>` : ""}</span>
          <span class="bank-kind">${KINDS[t.kind]}</span>
          <span class="bank-amount">${sign}${money(t.amount)}</span>
        </div>
        <div class="bank-fields ${transfer ? "transfer" : ""}">
          ${transfer ? "" : `<input class="bank-payee" value="${escapeHtml(t.payee)}" placeholder="${t.kind === "income" ? T("common.receivedFrom") : T("common.paidTo")}" aria-label="${t.kind === "income" ? T("common.receivedFrom") : T("common.paidTo")}">`}
          <input class="bank-note" value="${escapeHtml(t.description)}" placeholder="${T("import.noteOptional")}" aria-label="${T("common.note")}">
          ${transfer ? "" : t.splits ? `<span class="bank-split" title="${T("import.splitOverBudgetsYouCan")}">${
            t.splits.map((p) => `${escapeHtml(p.label)} <b>${money(p.amount)}</b>`).join("<br>")}</span>`
            : `<input class="bank-line" placeholder="${T("import.budgetOptional")}" aria-label="${T("common.budget")}">`}
        </div>
        ${t.missing?.length ? `<p class="bank-dup">${T("import.missingBudgets", { count: t.missing.length, names: t.missing.map((m) => `“${escapeHtml(m)}”`).join(", ") })}</p>` : ""}
        ${t.duplicate ? `<p class="bank-dup">${T("import.looksLikeItsAlreadyIn", { payee: escapeHtml(t.duplicate.payee || KINDS[t.kind]), date: shortDate(t.duplicate.date) })}</p>` : ""}
      </div>
    </li>`;
  }).join("");
  rows = transactions.map((t, i) => {
    const el = $(`#bank-list [data-i="${i}"]`);
    const input = el.querySelector(".bank-line");
    const budget = input && combobox(input, { options: () => lines, strict: true, empty: T("common.noBudgetWithThatName") });
    if (t.line) budget.set(t.line);
    return { t, el, budget };
  });
  $("#bank-error").textContent = "";
  update();
  $("#bank-dialog").showModal();
  $("#bank-dialog").scrollTop = 0;
}

const included = () => rows.filter((r) => r.el.querySelector(".bank-include input").checked);

function update() {
  rows.forEach((r) => r.el.classList.toggle("skipped", !r.el.querySelector(".bank-include input").checked));
  const n = included().length;
  $("#bank-add").textContent = n ? T("import.addCount", { count: n }) : T("import.nothingToAdd");
  $("#bank-add").disabled = !n;
}
$("#bank-list").addEventListener("change", (e) => e.target.matches(".bank-include input") && update());
$("#bank-list").addEventListener("input", (e) => e.target.matches(".bank-payee") && e.target.classList.remove("invalid"));

$("#bank-add").onclick = once(async () => {
  const chosen = included();
  const missing = chosen.filter((r) => r.el.querySelector(".bank-payee") && !r.el.querySelector(".bank-payee").value.trim());
  missing.forEach((r) => r.el.querySelector(".bank-payee").classList.add("invalid"));
  if (missing.length) {
    $("#bank-error").textContent = T("import.missingPayees", { count: missing.length });
    missing[0].el.querySelector(".bank-payee").focus();
    return;
  }
  const transactions = chosen.map(({ t, el, budget }) => ({
    date: t.date, paid_date: t.paid_date, amount: t.amount, kind: t.kind,
    payee: el.querySelector(".bank-payee")?.value.trim() || "",
    description: el.querySelector(".bank-note").value.trim(),
    line: budget?.value || null,
    splits: t.splits || null,
  }));
  const { added } = await api("/api/bank-import", { method: "POST", body: { transactions } });
  $("#bank-dialog").close();
  toast(T("import.addedCount", { count: added }));
  load();
});
