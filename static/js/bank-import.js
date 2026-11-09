// Importing transactions from a bank export (CSV). The server reads the file and suggests
// payees, budgets and likely duplicates; here every transaction is reviewed before any is added.
import { combobox } from "./controls.js";
import { DATE_LOCALE, escapeHtml, money, plural, shortDate } from "./format.js";
import { load } from "./overview.js";
import { $, api, once, toast } from "./ui.js";

const KINDS = { expense: "Expense", income: "Income", save: "To savings", withdraw: "From savings" };
let rows = []; // [{ t, include, budget (combobox) }]

$("#bank-import-btn").onclick = () => $("#bank-file").click();
$("#bank-file").onchange = async (e) => {
  const file = e.target.files[0];
  e.target.value = ""; // so the same file can be chosen again
  if (!file) return;
  const preview = await api("/api/bank-import-preview", { method: "POST", body: await file.arrayBuffer() });
  open(preview);
};

const weekday = (iso) => new Date(`${iso}T00:00`).toLocaleDateString(DATE_LOCALE, { weekday: "short" });

function open({ bank, transactions, lines }) {
  const duplicates = transactions.filter((t) => t.duplicate).length;
  $("#bank-title").textContent = `Review ${plural(transactions.length, "transaction")} from ${bank}`;
  $("#bank-hint").textContent = "Check each one and choose a budget where you like. Uncheck any you don't want to add." +
    (duplicates === 1 ? " 1 transaction seems to be in Budget already, so it's unchecked."
      : duplicates ? ` ${duplicates} transactions seem to be in Budget already, so they're unchecked.` : "");
  $("#bank-list").innerHTML = transactions.map((t, i) => {
    const transfer = t.kind === "save" || t.kind === "withdraw";
    const sign = t.kind === "income" || t.kind === "withdraw" ? "+ " : "";
    return `<li class="bank-row" data-i="${i}">
      <label class="bank-include" aria-label="Add this transaction"><input type="checkbox" ${t.duplicate ? "" : "checked"}></label>
      <div class="bank-main">
        <div class="bank-top">
          <span>${weekday(t.date)} ${shortDate(t.date)}${t.paid_date ? ` <span class="muted">· left your bank ${shortDate(t.paid_date)}</span>` : ""}</span>
          <span class="bank-kind">${KINDS[t.kind]}</span>
          <span class="bank-amount">${sign}${money(t.amount)}</span>
        </div>
        <div class="bank-fields ${transfer ? "transfer" : ""}">
          ${transfer ? "" : `<input class="bank-payee" value="${escapeHtml(t.payee)}" placeholder="${t.kind === "income" ? "Received from" : "Paid to"}" aria-label="${t.kind === "income" ? "Received from" : "Paid to"}">`}
          <input class="bank-note" value="${escapeHtml(t.description)}" placeholder="Note (optional)" aria-label="Note">
          ${transfer ? "" : t.splits ? `<span class="bank-split" title="Split over budgets: you can change it after adding">${
            t.splits.map((p) => `${escapeHtml(p.label)} <b>${money(p.amount)}</b>`).join("<br>")}</span>`
            : `<input class="bank-line" placeholder="Budget (optional)" aria-label="Budget">`}
        </div>
        ${t.missing?.length ? `<p class="bank-dup">${t.missing.map((m) => `“${escapeHtml(m)}”`).join(", ")} ${t.missing.length === 1 ? "isn't a budget" : "aren't budgets"} here, so that part stays outside a budget. You can choose one after adding.</p>` : ""}
        ${t.duplicate ? `<p class="bank-dup">Looks like it's already in Budget: ${escapeHtml(t.duplicate.payee || KINDS[t.kind])} on ${shortDate(t.duplicate.date)}.</p>` : ""}
      </div>
    </li>`;
  }).join("");
  rows = transactions.map((t, i) => {
    const el = $(`#bank-list [data-i="${i}"]`);
    const input = el.querySelector(".bank-line");
    const budget = input && combobox(input, { options: () => lines, strict: true, empty: "No budget with that name" });
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
  $("#bank-add").textContent = n ? `Add ${plural(n, "transaction")}` : "Nothing to add";
  $("#bank-add").disabled = !n;
}
$("#bank-list").addEventListener("change", (e) => e.target.matches(".bank-include input") && update());
$("#bank-list").addEventListener("input", (e) => e.target.matches(".bank-payee") && e.target.classList.remove("invalid"));

$("#bank-add").onclick = once(async () => {
  const chosen = included();
  const missing = chosen.filter((r) => r.el.querySelector(".bank-payee") && !r.el.querySelector(".bank-payee").value.trim());
  missing.forEach((r) => r.el.querySelector(".bank-payee").classList.add("invalid"));
  if (missing.length) {
    $("#bank-error").textContent = `Fill in who was paid (or who paid you) for ${plural(missing.length, "transaction")}, or uncheck ${missing.length === 1 ? "it" : "them"}.`;
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
  toast(`${plural(added, "transaction")} added`);
  load();
});
