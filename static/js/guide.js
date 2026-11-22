// The getting-started guide on the overview: the steps a new user takes, each ticked off by
// itself once it's done (the server says which are, GET /api/setup). The card goes away when
// every step is done, or when the user hides it. Each step's button opens what the page
// already has for it, so the guide adds no second way of doing anything.
//
// In Simple mode it's two steps: budgets and spending. Keeping the bank balance is offered later.
//
// Afterwards, the same place offers one feature at a time beyond the basics, once it's useful
// (the server decides when, see offers() in app/api.py): turning it on, or Not now.
import { openAccount } from "./accounts.js";
import { monthOnly } from "./format.js";
import { html, setHtml } from "./html.js";
import { t } from "./i18n.js";
import { updateSettings } from "./settings.js";
import { isSimple, state } from "./state.js";
import { $, api, once, toast } from "./ui.js";

const open = (selector) => $(selector).click();
const STEPS = [
  {
    extended: true, // with only the basics, it's offered once the user keeps Budget for a while
    done: (s) => s.bank,
    title: () => t("guide.enterYourBankBalance"),
    text: () => t("guide.whatsInYourBankAccount"),
    actions: () => [{ label: t("guide.setUpBankAccount"), run: () => openAccount("bank") }],
  },
  {
    done: (s) => s.budgets,
    title: () => t("guide.setUpYourBudgets"),
    text: () => t("guide.startFromYourIncomeThen"),
    actions: () => [{ label: t("common.setUpBudgets"), run: () => open("#manage-btn") }],
  },
  {
    done: (s) => s.transaction,
    title: () => t("guide.addWhatYouSpend"),
    text: () => t("guide.addAnExpenseYourselfOr"),
    actions: () => [{ label: t("guide.addAnExpense"), run: () => open("#add-btn") }, { label: t("common.import"), link: true, run: () => open("#bank-import-btn") }],
  },
];

const activeSteps = () => STEPS.filter((step) => !step.extended || !isSimple());

// What each offer says, and what turning it on does.
const OFFERS = {
  bank: () => ({
    title: t("guide.offerBankTitle"),
    text: t("guide.offerBankText"),
    accept: t("guide.setUpBankAccount"),
    run: () => openAccount("bank"),
  }),
  outlook: () => ({
    title: t("guide.planAheadWithTheOutlook"),
    text: t("guide.youveKeptBudgetForA"),
    accept: t("guide.turnOnExtended"),
    run: async () => {
      await updateSettings({ mode: "full" });
      location.hash = "#outlook";
      toast(t("guide.extendedOnChange"), 3);
    },
  }),
  carry: (o) => ({
    title: t("guide.keepWhatsLeftForNext"),
    text: t("guide.hadMoneyLeftInAnd",
      { name: o.name, first: monthOnly(o.months[0], "long"), second: monthOnly(o.months[1], "long") }),
    accept: t("guide.turnOnExtended"),
    run: async () => {
      await updateSettings({ mode: "full" });
      toast(t("guide.extendedOnCarry"), 4);
    },
  }),
  savings: () => ({
    title: t("guide.keepTrackOfYourSavings"),
    text: t("guide.youveMovedMoneyToOr"),
    accept: t("guide.setUpSavings"),
    run: () => openAccount("savings"),
  }),
};

let actions = []; // what the buttons now on the card do, by their data-run number
let offer = null; // the offer on the card

export async function renderGuide() {
  if (["#outlook", "#history"].includes(location.hash)) return; // it's on the overview
  const { steps, hidden, offers } = await api("/api/setup");
  const shown = activeSteps();
  const done = shown.filter((step) => step.done(steps)).length;
  $("#guide").hidden = hidden || done === shown.length;
  renderOffer($("#guide").hidden ? offers[0] : null);
  if ($("#guide").hidden) return;
  $("#guide-progress").textContent = t("guide.ofDone", { done, total: shown.length });
  actions = [];
  const next = shown.find((step) => !step.done(steps)); // its button stands out
  setHtml($("#guide-steps"), html`${shown.map((step) => {
    const finished = step.done(steps);
    const buttons = finished ? "" : step.actions().map((a) => {
      actions.push(a.run);
      return html`<button type="button" class="${a.link ? "link-btn" : step === next ? "primary-btn" : "ghost-btn"}" data-run="${actions.length - 1}">${a.label}</button>`;
    });
    return html`<li class="guide-step ${finished ? "done" : ""}">
      <span class="guide-mark" aria-hidden="true"></span>
      <div><b>${step.title()}</b>${finished ? html`<span class="visually-hidden"> ${t("guide.done")}</span>` : html`<span class="muted">${step.text()}</span>`}</div>
      <span class="guide-actions">${buttons}</span>
    </li>`;
  })}`);
}

function renderOffer(found) {
  offer = found || null;
  $("#offer").hidden = !offer;
  if (!offer) return;
  const o = OFFERS[offer.id](offer);
  setHtml($("#offer"), html`
    <div class="offer-text"><b>${o.title}</b><span class="muted">${o.text}</span></div>
    <span class="offer-actions">
      <button type="button" class="link-btn" id="offer-later">${t("guide.notNow")}</button>
      <button type="button" class="ghost-btn" id="offer-accept">${o.accept}</button>
    </span>`);
  $("#offer-accept").onclick = once(async () => {
    await o.run();
    renderGuide();
  });
  $("#offer-later").onclick = once(async () => {
    const dismissed = [...new Set([...state.settings.offers_dismissed.split(",").filter(Boolean), offer.id])].join(",");
    await updateSettings({ offers_dismissed: dismissed });
    renderGuide();
  });
}

$("#guide-steps").onclick = (e) => {
  const button = e.target.closest("[data-run]");
  if (button) actions[Number(button.dataset.run)]();
};
$("#guide-hide").onclick = once(async () => {
  state.settings.guide = "hidden";
  await api("/api/settings", { method: "POST", body: { guide: "hidden" } });
  $("#guide").hidden = true;
  toast(t("guide.guideHidden"));
  renderGuide();
});

// Steps get done all over the page: look again whenever data changed or the overview comes back.
document.addEventListener("data-changed", renderGuide);
addEventListener("hashchange", renderGuide);
