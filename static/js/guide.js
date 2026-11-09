// The getting-started guide on the overview: the steps a new user takes, each ticked off by
// itself once it's done (the server says which are, GET /api/setup). The card goes away when
// every step is done, or when the user hides it. Each step's button opens what the page
// already has for it, so the guide adds no second way of doing anything.
import { state } from "./state.js";
import { $, api, once, toast } from "./ui.js";

const open = (selector) => $(selector).click();
const STEPS = [
  {
    done: (s) => s.bank && s.savings,
    title: "Enter your balances",
    text: (s) => (s.bank ? "Your bank account is set. Now your savings: enter 0 if you have none." : "What's in your bank account and savings today. Budget keeps count from there, and can tell you when a transaction is missing."),
    actions: (s) => [{ label: s.bank ? "Set up savings" : "Set up bank account", run: () => open(`.account-row[data-account="${s.bank ? "savings" : "bank"}"]`) }],
  },
  {
    done: (s) => s.budgets,
    title: "Set up your budgets",
    text: () => "Give each kind of spending an amount per month, like Rent, Groceries or Fun money.",
    actions: () => [{ label: "Set up budgets", run: () => open("#manage-btn") }],
  },
  {
    done: (s) => s.transaction,
    title: "Add what you spend",
    text: () => "Add an expense yourself, or import your transactions from your bank (ING for now).",
    actions: () => [{ label: "Add an expense", run: () => open("#add-btn") }, { label: "Import", link: true, run: () => open("#bank-import-btn") }],
  },
  {
    done: (s) => s.income,
    title: "Look ahead",
    text: () => "Add the income you expect, like your salary. The Outlook then shows where your savings are heading.",
    actions: () => [{ label: "Add expected income", run: () => { location.hash = "#outlook"; open('[data-add-plan="income"]'); } }],
  },
];

let actions = []; // what the buttons now on the card do, by their data-run number

export async function renderGuide() {
  if (["#outlook", "#history"].includes(location.hash)) return; // it's on the overview
  const { steps, hidden } = await api("/api/setup");
  const done = STEPS.filter((step) => step.done(steps)).length;
  $("#guide").hidden = hidden || done === STEPS.length;
  if ($("#guide").hidden) return;
  $("#guide-progress").textContent = `${done} of ${STEPS.length} done`;
  actions = [];
  const next = STEPS.find((step) => !step.done(steps)); // its button stands out
  $("#guide-steps").innerHTML = STEPS.map((step) => {
    const finished = step.done(steps);
    const buttons = finished ? "" : step.actions(steps).map((a) => {
      actions.push(a.run);
      return `<button type="button" class="${a.link ? "link-btn" : step === next ? "primary-btn" : "ghost-btn"}" data-run="${actions.length - 1}">${a.label}</button>`;
    }).join("");
    return `<li class="guide-step ${finished ? "done" : ""}">
      <span class="guide-mark" aria-hidden="true"></span>
      <div><b>${step.title}</b>${finished ? `<span class="visually-hidden"> (done)</span>` : `<span class="muted">${step.text(steps)}</span>`}</div>
      <span class="guide-actions">${buttons}</span>
    </li>`;
  }).join("");
}

$("#guide-steps").onclick = (e) => {
  const button = e.target.closest("[data-run]");
  if (button) actions[Number(button.dataset.run)]();
};
$("#guide-hide").onclick = once(async () => {
  state.settings.guide = "hidden";
  await api("/api/settings", { method: "POST", body: { guide: "hidden" } });
  $("#guide").hidden = true;
  toast("Guide hidden");
});

// Steps get done all over the page: look again whenever data changed or the overview comes back.
document.addEventListener("data-changed", renderGuide);
addEventListener("hashchange", renderGuide);
