// A small line chart: months on x, money (cents) on y, a crosshair and tooltip on hover.
// Used for the balance development and the savings outlook.
import { money, monthOnly } from "./format.js";

// series: [{ name, values (cents, null = no value), cls, dots = true, against }]
//   against: values of another series; the line is drawn green above it and red below.
// options: height, ticks (number of steps), includeZero, tooltip(i) -> html, label(i) -> x-axis text
export function lineChart(el, months, series, { height = 220, ticks: steps = 4, includeZero = false, tooltip, label = (i) => monthOnly(months[i]) } = {}) {
  const W = el.clientWidth || 600, H = height, pad = { l: 60, r: 12, t: 12, b: 24 };
  const all = series.flatMap((s) => s.values).filter((v) => v !== null);
  if (!all.length) return (el.innerHTML = "");
  let lo = Math.min(...all, ...(includeZero ? [0] : [])), hi = Math.max(...all);
  if (hi - lo < 100) { lo -= 5000; hi += 5000; } // a flat line: show some room around it
  const raw = (hi - lo) / steps, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((f) => f * mag).find((v) => v >= raw);
  lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
  const n = months.length, band = (W - pad.l - pad.r) / n;
  const x = (i) => pad.l + (i + 0.5) * band;
  const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b);
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(v);
  // Paths break where a value is missing.
  const path = (values) => values.map((v, i) => (v === null ? "" : `${i && values[i - 1] !== null ? "L" : "M"}${x(i)},${y(v)}`)).join("");

  el.innerHTML = `<svg width="${W}" height="${H}" role="img" aria-label="${series.map((s) => s.name).join(" and ")} per month">
    ${ticks.map((v) => `<line class="grid ${v === 0 ? "zero" : ""}" x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/>
      <text class="axis" x="${pad.l - 8}" y="${y(v) + 4}" text-anchor="end">${money(v, { whole: true })}</text>`).join("")}
    ${months.map((_, i) => `<text class="axis" x="${x(i)}" y="${H - 6}" text-anchor="middle">${label(i)}</text>`).join("")}
    <line class="crosshair" x1="0" x2="0" y1="${pad.t}" y2="${H - pad.b}" hidden/>
    ${series.map((s) => {
      const d = path(s.values);
      if (!s.against) return `<path class="${s.cls}" d="${d}"/>`;
      // Green where the line is above the other series, red where it's below: the same
      // line drawn twice, each clipped to one side of the other series.
      const edge = s.against.map((v, i) => `${i ? "L" : "M"}${i ? x(i) : 0},${y(v)}`).join("") + `L${W},${y(s.against.at(-1))}`;
      const id = `clip${Math.random().toString(36).slice(2)}`;
      return `<clipPath id="${id}a"><path d="${edge}L${W},0L0,0Z"/></clipPath>
        <clipPath id="${id}b"><path d="${edge}L${W},${H}L0,${H}Z"/></clipPath>
        <path class="${s.cls} good" d="${d}" clip-path="url(#${id}a)"/>
        <path class="${s.cls} bad" d="${d}" clip-path="url(#${id}b)"/>`;
    }).join("")}
    ${series.filter((s) => s.dots !== false).map((s) => s.values.map((v, i) => v === null ? "" : `<circle class="dot ${
      s.against ? (v < s.against[i] ? "bad" : "good") : ""}" cx="${x(i)}" cy="${y(v)}" r="4"/>`).join("")).join("")}
    ${months.map((_, i) => series.some((s) => s.values[i] !== null)
      ? `<rect class="hit" data-i="${i}" x="${x(i) - band / 2}" y="${pad.t}" width="${band}" height="${H - pad.t - pad.b}"/>` : "").join("")}
  </svg><div class="hist-tip" hidden></div>`;

  const tip = el.querySelector(".hist-tip"), cross = el.querySelector(".crosshair");
  el.querySelectorAll(".hit").forEach((r) => {
    r.onmouseenter = () => {
      const i = Number(r.dataset.i);
      tip.innerHTML = tooltip(i);
      tip.hidden = false;
      tip.style.left = `${Math.min(Math.max(x(i) - tip.offsetWidth / 2, 0), W - tip.offsetWidth)}px`;
      const top = Math.max(...series.map((s) => s.values[i]).filter((v) => v !== null));
      tip.style.top = `${Math.max(y(top) - tip.offsetHeight - 12, 0)}px`;
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.hidden = false;
    };
    r.onmouseleave = () => { tip.hidden = true; cross.hidden = true; };
  });
}
