// Custom form controls (month picker, date picker, combobox) that look the same in
// every browser. They share one popover at a time, positioned under their anchor.
import { DATE_LOCALE, currentMonth, escapeHtml, isoDate, monthName, monthOnly, pad, shiftMonth } from "./format.js";

const popovers = {
  current: null, // { anchor, panel }
  open(anchor, panel) {
    this.close();
    // Panels live next to their anchor (so they work inside modal dialogs) but are
    // position: fixed, so no container clips them.
    const r = anchor.getBoundingClientRect();
    panel.style.minWidth = `${r.width}px`;
    panel.hidden = false;
    const below = r.bottom + 6 + panel.offsetHeight <= innerHeight || r.top < panel.offsetHeight;
    panel.style.top = `${below ? r.bottom + 6 : r.top - 6 - panel.offsetHeight}px`;
    panel.style.left = `${Math.max(8, Math.min(r.left, innerWidth - panel.offsetWidth - 8))}px`;
    this.current = { anchor, panel };
  },
  close() {
    if (!this.current) return;
    this.current.panel.hidden = true;
    this.current = null;
  },
  isOpen(panel) {
    return this.current?.panel === panel;
  },
};
document.addEventListener("mousedown", (e) => {
  const c = popovers.current;
  if (c && !c.panel.contains(e.target) && !c.anchor.contains(e.target)) popovers.close();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && popovers.current) {
    e.preventDefault(); // close the popover, not the surrounding dialog
    popovers.close();
  }
}, true);
document.addEventListener("scroll", (e) => {
  if (popovers.current && !popovers.current.panel.contains(e.target)) popovers.close();
}, true);
addEventListener("resize", () => popovers.close());

function makePanel(anchor, className) {
  const panel = document.createElement("div");
  panel.className = `popover ${className}`;
  panel.hidden = true;
  anchor.after(panel);
  return panel;
}

// Menu: clicking `button` shows a short list of choices; items() returns their HTML
// (links or buttons with class "opt"). Choosing one closes it.
export function menu(button, items) {
  // On the page itself: inside a frosted card (backdrop-filter), position: fixed would be
  // relative to the card.
  const panel = document.body.appendChild(Object.assign(document.createElement("div"), { className: "popover menu-pop", hidden: true }));
  panel.setAttribute("role", "menu");
  button.setAttribute("aria-haspopup", "menu");
  button.addEventListener("click", () => {
    if (popovers.isOpen(panel)) return popovers.close();
    panel.innerHTML = items();
    popovers.open(button, panel);
    // Keep it under the button's right edge: the button sits at the end of a row.
    const r = button.getBoundingClientRect();
    panel.style.left = `${Math.max(8, Math.min(r.right - panel.offsetWidth, innerWidth - panel.offsetWidth - 8))}px`;
  });
  panel.addEventListener("click", (e) => e.target.closest(".opt") && popovers.close());
  return panel;
}

// Month picker: clicking `button` shows a year with 12 months. get() / set() read and write "YYYY-MM".
export function monthPicker(button, { get, set }) {
  const panel = makePanel(button, "month-pop");
  let year;
  const render = () => {
    panel.innerHTML = `
      <div class="pop-head">
        <button type="button" class="pop-nav" data-year="-1" aria-label="Previous year">‹</button>
        <b>${year}</b>
        <button type="button" class="pop-nav" data-year="1" aria-label="Next year">›</button>
      </div>
      <div class="month-grid">${Array.from({ length: 12 }, (_, i) => {
        const ym = `${year}-${pad(i + 1)}`;
        return `<button type="button" data-month="${ym}" class="${ym === get() ? "selected" : ""} ${ym === currentMonth() ? "today" : ""}">${monthOnly(ym)}</button>`;
      }).join("")}</div>`;
  };
  button.addEventListener("click", () => {
    if (popovers.isOpen(panel)) return popovers.close();
    year = Number(get().slice(0, 4));
    render();
    popovers.open(button, panel);
  });
  panel.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.year) {
      year += Number(b.dataset.year);
      render();
    } else {
      popovers.close();
      set(b.dataset.month);
    }
  });
}

// Date picker: `button` shows the date, `input` (hidden) holds "YYYY-MM-DD".
// onChange is called when the user picks a date.
export function datePicker(button, input, { onChange } = {}) {
  const panel = makePanel(button, "date-pop");
  let view; // "YYYY-MM" shown in the calendar
  const label = () => {
    const d = new Date(input.value + "T00:00");
    const sameYear = d.getFullYear() === new Date().getFullYear();
    button.textContent = d.toLocaleDateString(DATE_LOCALE, { weekday: "short", day: "numeric", month: "long", ...(sameYear ? {} : { year: "numeric" }) });
  };
  const render = () => {
    const [y, m] = view.split("-").map(Number);
    const offset = (new Date(y, m - 1, 1).getDay() + 6) % 7; // weeks start on Monday
    const days = new Date(y, m, 0).getDate();
    const today = isoDate(new Date());
    const weekdays = Array.from({ length: 7 }, (_, i) =>
      `<span>${new Date(2024, 0, 1 + i).toLocaleDateString(DATE_LOCALE, { weekday: "narrow" })}</span>`).join("");
    const cells = Array.from({ length: offset }, () => "<span></span>").join("") +
      Array.from({ length: days }, (_, i) => {
        const iso = `${view}-${pad(i + 1)}`;
        return `<button type="button" data-date="${iso}" class="${iso === input.value ? "selected" : ""} ${iso === today ? "today" : ""}">${i + 1}</button>`;
      }).join("");
    panel.innerHTML = `
      <div class="pop-head">
        <button type="button" class="pop-nav" data-shift="-1" aria-label="Previous month">‹</button>
        <b>${monthName(view)}</b>
        <button type="button" class="pop-nav" data-shift="1" aria-label="Next month">›</button>
      </div>
      <div class="cal-grid weekdays">${weekdays}</div>
      <div class="cal-grid">${cells}</div>
      <div class="pop-foot"><button type="button" class="link-btn" data-date="${today}">Today</button></div>`;
  };
  button.addEventListener("click", () => {
    if (popovers.isOpen(panel)) return popovers.close();
    view = input.value.slice(0, 7);
    render();
    popovers.open(button, panel);
  });
  panel.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.shift) {
      view = shiftMonth(view, Number(b.dataset.shift));
      render();
    } else {
      picker.set(b.dataset.date);
      popovers.close();
      onChange?.(b.dataset.date);
    }
  });
  const picker = {
    set(value) {
      input.value = value;
      label();
    },
  };
  return picker;
}

// Combobox: a text input with a filterable list of options.
// options() returns [{ value, label, group?, display? }]. With strict: true, only a listed
// option can be chosen (value is null until one is); otherwise any text is allowed.
export function combobox(input, { options, strict = false, onSelect, empty = "No matches" }) {
  const panel = makePanel(input, "combo-pop");
  input.autocomplete = "off";
  input.setAttribute("role", "combobox");
  let shown = [];
  let active = -1;
  let selected = null;

  const render = (query) => {
    const q = query.trim().toLowerCase();
    shown = options().filter((o) => !q || `${o.group || ""} ${o.label}`.toLowerCase().includes(q));
    if (!shown.length && !strict) return popovers.close();
    let lastGroup;
    panel.innerHTML = shown.length
      ? shown.map((o, i) => {
          const head = o.group && o.group !== lastGroup ? `<div class="opt-group">${escapeHtml(o.group)}</div>` : "";
          lastGroup = o.group;
          return `${head}<div class="opt ${o.group ? "indent" : ""} ${i === active ? "active" : ""}" data-i="${i}">${escapeHtml(o.label)}</div>`;
        }).join("")
      : `<div class="opt-empty">${empty}</div>`;
    if (!popovers.isOpen(panel)) popovers.open(input, panel);
    panel.querySelector(".active")?.scrollIntoView({ block: "nearest" });
  };
  const choose = (o) => {
    selected = o.value;
    input.value = o.display || o.label;
    popovers.close();
    onSelect?.(o);
  };

  input.addEventListener("focus", () => {
    active = -1;
    render(strict ? "" : input.value);
  });
  input.addEventListener("click", () => popovers.isOpen(panel) || render(strict ? "" : input.value));
  input.addEventListener("input", () => {
    selected = null;
    active = 0;
    render(input.value);
  });
  input.addEventListener("keydown", (e) => {
    const open = popovers.isOpen(panel);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) return render(strict ? "" : input.value);
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length;
      render(strict && selected !== null ? "" : input.value);
    } else if ((e.key === "Enter" || e.key === "Tab") && open && shown[active]) {
      if (e.key === "Enter") e.preventDefault();
      choose(shown[active]);
    }
  });
  input.addEventListener("blur", () => {
    if (popovers.isOpen(panel)) popovers.close();
    if (strict && selected === null) {
      const match = options().find((o) => [o.label, o.display].some((t) => t?.toLowerCase() === input.value.trim().toLowerCase()));
      match ? choose(match) : (input.value = "");
    }
  });
  panel.addEventListener("mousedown", (e) => {
    e.preventDefault(); // keep focus in the input
    const el = e.target.closest(".opt");
    if (el) choose(shown[el.dataset.i]);
  });

  return {
    get value() {
      return strict ? selected : input.value.trim();
    },
    set(value) {
      const o = options().find((o) => o.value === value);
      if (o) {
        selected = o.value;
        input.value = o.display || o.label;
      }
    },
    clear() {
      selected = null;
      input.value = "";
    },
  };
}
