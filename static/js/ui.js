// Small helpers shared by every part of the page: the API, toasts and modals.
export const $ = (sel) => document.querySelector(sel);

// Calls the app's API. Shows a friendly message (and throws) when something fails.
export async function api(path, options = {}) {
  let res, data;
  try {
    const file = options.body instanceof ArrayBuffer; // an imported file is sent as it is
    res = await fetch(path, {
      headers: { "Content-Type": file ? "application/octet-stream" : "application/json" },
      ...options,
      body: file ? options.body : options.body && JSON.stringify(options.body),
    });
    data = await res.json();
  } catch {
    // The server isn't answering (stopped, or restarted mid-request).
    alertDialog("Budget isn't responding right now. Your data is safe. Quit Budget and open it again.",
      "Can't reach the app");
    throw new Error("Server not reachable");
  }
  if (!res.ok) {
    alertDialog(data.error || "Something went wrong. Reload the page and try again.");
    throw new Error(data.error);
  }
  return data;
}

// A short message at the bottom. Where popovers are supported it's one, so it shows above an
// open dialog too. It's also hidden with `hidden`, so older WebKit (which ignores the popover
// attribute and would show an empty pill) only shows it while there's a message.
const popovers = typeof HTMLElement.prototype.showPopover === "function";
export function toast(message, seconds = 2.2) {
  const el = $("#toast");
  el.textContent = message;
  el.hidden = false;
  if (popovers) {
    if (el.matches(":popover-open")) el.hidePopover();
    el.showPopover(); // shown last, so on top of any dialog
  }
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    el.hidden = true;
    if (popovers && el.matches(":popover-open")) el.hidePopover();
  }, seconds * 1000);
}

// Confirm / alert modals in the app's own style (instead of the browser's popups).
// Resolves true when confirmed; Escape or Cancel resolve false.
export function confirmDialog({ title, message = "", confirm = "OK", cancel = "Cancel", danger = false }) {
  const d = $("#confirm-dialog");
  d.querySelector("h2").textContent = title;
  d.querySelector("p").textContent = message;
  d.querySelector("p").hidden = !message;
  const ok = d.querySelector("[value=ok]");
  ok.textContent = confirm;
  ok.className = danger ? "danger-btn" : "primary-btn";
  d.querySelector("[value=cancel]").hidden = cancel === null;
  d.querySelector("[value=cancel]").textContent = cancel || "";
  d.returnValue = "";
  d.showModal();
  ok.focus();
  return new Promise((resolve) => (d.onclose = () => resolve(d.returnValue === "ok")));
}
export const alertDialog = (message, title = "That didn't work") => confirmDialog({ title, message, cancel: null });

// Shows (or clears, with an empty message) the error under a form field.
export function fieldError(form, name, message) {
  const el = form.querySelector(`[data-error="${name}"]`);
  if (!el) return;
  el.textContent = message;
  el.closest(".field").classList.toggle("invalid", !!message);
}

// Close buttons in dialogs.
document.addEventListener("click", (e) => e.target.closest("[data-close]")?.closest("dialog").close());

// Table headers that explain their column when hovered or focused: tipHead() makes the
// header, columnTips(table) shows the explanation. It floats over the page, so a table that
// scrolls sideways can't clip it.
export const tipHead = (label, tip) => tip ? `<th tabindex="0" data-tip="${tip}">${label}</th>` : `<th>${label}</th>`;
const columnTip = document.body.appendChild(Object.assign(document.createElement("div"), { className: "col-tip", hidden: true }));
function showColumnTip(th) {
  columnTip.textContent = th.dataset.tip;
  columnTip.hidden = false;
  const box = th.getBoundingClientRect();
  columnTip.style.left = `${Math.max(8, Math.min(box.right - columnTip.offsetWidth, innerWidth - columnTip.offsetWidth - 8))}px`;
  columnTip.style.top = `${box.bottom + 6}px`;
}
const hideColumnTip = () => (columnTip.hidden = true);
addEventListener("scroll", hideColumnTip, { passive: true });
export function columnTips(table) {
  table.addEventListener("mouseover", (e) => e.target.closest("th[data-tip]") && showColumnTip(e.target.closest("th[data-tip]")));
  table.addEventListener("mouseout", (e) => e.target.closest("th[data-tip]") && hideColumnTip());
  table.addEventListener("focusin", (e) => e.target.matches("th[data-tip]") && showColumnTip(e.target));
  table.addEventListener("focusout", hideColumnTip);
}
