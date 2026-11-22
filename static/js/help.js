// Small "?" buttons that explain a word or a number in plain language, for people who
// haven't kept a budget before. helpTip("carry") makes one; the static page has them as
// <button class="help-tip" data-help="...">. Clicking one shows its text under it. A heading can
// explain itself too: <button class="help-label" data-help="..."> (underlined with dots).
import { popup } from "./controls.js";
import { t } from "./i18n.js";

const HELP = {
  budgets: () => t("help.budgets"),
  carry: () => t("help.carry"),
  "no-budget": () => t("help.noBudget"),
  ready: () => t("help.ready"),
  balance: () => t("help.balance"),
  "starting-point": () => t("help.startingPoint"),
  fit: () => t("help.fit"),
  buffer: () => t("help.buffer"),
  free: () => t("help.free"),
  outlook: () => t("help.outlook"),
};

export const helpTip = (key) =>
  `<button type="button" class="help-tip" data-help="${key}" aria-label="${t("help.whatDoesThisMean")}">?</button>`;

// In the capture phase, so a "?" inside a clickable row only explains and doesn't click the row.
document.addEventListener("click", (e) => {
  const button = e.target.closest(".help-tip, .help-label");
  if (!button) return;
  e.preventDefault();
  e.stopPropagation();
  popup(button, `<p class="help-text">${HELP[button.dataset.help]?.() ?? ""}</p>`);
}, true);
document.querySelectorAll(".help-tip").forEach((b) => b.setAttribute("aria-label", t("help.whatDoesThisMean")));
