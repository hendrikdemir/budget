// Shared state of the page. Modules read and update it; the overview re-renders from it.
const now = new Date();

export const PRESETS = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#ec4899", "#8b5cf6", "#334155"];

export const state = {
  settings: { accent: PRESETS[0], theme: "system", currency: "EUR" },
  month: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`, // the month being viewed
  // Everything about the viewed month, from GET /api/month: categories, transactions,
  // groups (budget lines per category), totals, leftover and outlook.
  data: null,
  payees: [], // [{ name, kind, line }]
  filter: null, // { key, label }: only transactions on a budget line ("i1"/"c1"), category ("k1") or uncategorized ("u")
  search: { query: "", type: "all", allMonths: false },
  allTransactions: null, // every month's transactions, loaded when searching all months
  selecting: false,
  selected: new Set(),
};

// Budget lines are keyed "i<id>" for items and "c<id>" for categories without items.
export const lineBody = (key) => ({ [key[0] === "i" ? "item_id" : "category_id"]: Number(key.slice(1)) });
export const splitKey = (s) => (s.item_id ? `i${s.item_id}` : `c${s.category_id}`);
// The part of a transaction not on any budget line.
export const uncategorized = (t) => t.amount - t.splits.reduce((sum, s) => sum + s.amount, 0);
export const isTransfer = (t) => t.kind === "save" || t.kind === "withdraw";
