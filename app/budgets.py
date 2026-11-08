"""Budgets, transactions and what a month looks like.

- A category (e.g. "Home") optionally holds items (e.g. "Electricity"). Budgets are set
  on items, or on the category itself when it has no items. Together: "budget lines",
  keyed "i<id>" (item) or "c<id>" (category).
- Budgets have a history: each row in `budgets` applies from its start month until the
  next row for the same line; an amount of NULL means "ended". Changing a budget from a
  month onward never alters earlier months.
- Each budget version says whether leftovers carry over to the next month by default;
  `rollover_choices` overrides that for a single month.
- A transaction (table `expenses`) is an expense, income, or a savings transfer ('save'
  bank -> savings, 'withdraw' savings -> bank). Expenses are split over zero or more
  budget lines (`splits`); what the splits don't cover is uncategorized. Income splits
  add extra budget to a line for that month. Transfers don't touch budgets.
"""
from .money import ApiError, GENERIC_ERROR, current_month, next_month

FIRST_MONTH = "0000-01"  # start month for budgets that have always applied


# ---- Budget history ----

def target_column(body):
    """("item_id" | "category_id", id) for the budget line in a request."""
    if body.get("item_id"):
        return "item_id", int(body["item_id"])
    if body.get("category_id"):
        return "category_id", int(body["category_id"])
    raise ApiError(GENERIC_ERROR)


def version_at(conn, column, target_id, month):
    return conn.execute(
        f"SELECT amount_cents, rollover FROM budgets WHERE {column} = ? AND start_month <= ? "
        "ORDER BY start_month DESC LIMIT 1",
        (target_id, month),
    ).fetchone()


def set_budget(conn, column, target_id, month, amount, rollover=None):
    """Make `amount` (None = ended) the budget from `month` until the next change.
    `rollover` of None keeps the current carry-over setting."""
    conn.execute(f"DELETE FROM budgets WHERE {column} = ? AND start_month = ?", (target_id, month))
    previous = version_at(conn, column, target_id, month)
    if rollover is None:
        rollover = bool(previous and previous["rollover"])
    rollover = int(bool(rollover)) if amount is not None else 0
    unchanged = (previous["amount_cents"], previous["rollover"]) == (amount, rollover) if previous else amount is None
    if not unchanged:
        conn.execute(
            f"INSERT INTO budgets ({column}, start_month, amount_cents, rollover) VALUES (?, ?, ?, ?)",
            (target_id, month, amount, rollover),
        )


def end_budget(conn, column, target_id, month):
    """End a budget from `month` onward, dropping any changes planned after it."""
    set_budget(conn, column, target_id, month, None)
    conn.execute(f"DELETE FROM budgets WHERE {column} = ? AND start_month > ?", (target_id, month))


def has_history_before(conn, column, target_id, month):
    return conn.execute(
        f"SELECT 1 FROM budgets WHERE {column} = ? AND start_month < ? AND amount_cents IS NOT NULL",
        (target_id, month),
    ).fetchone() is not None


def is_active(conn, column, target_id, month):
    version = version_at(conn, column, target_id, month)
    return bool(version) and version["amount_cents"] is not None


class Line:
    """One budget line's history, spending and carry-over choices. The leftover carried into
    each month is worked out by walking its history once, from the line's first month, and
    remembered: asking about many months (History, Outlook) doesn't walk it again each time."""

    def __init__(self, versions, spent, extra, choices, first_month):
        # versions: [{start_month, amount_cents, rollover}] sorted; spent/extra/choices: {month: value}.
        self.versions, self.spent, self.extra, self.choices = versions, spent, extra, choices
        # Budgets that have always applied count from the first month with transactions.
        starts = [v["start_month"] for v in versions if v["start_month"] != FIRST_MONTH]
        if first_month and any(v["start_month"] == FIRST_MONTH for v in versions):
            starts.append(first_month)
        self.start = min(starts, default=None)
        self.carried = {}  # month -> leftover carried into it, for the months walked so far
        self.walked, self.carry = self.start, 0  # the next month to walk, and what's carried into it

    def version_at(self, month):
        return next((v for v in reversed(self.versions) if v["start_month"] <= month), None)

    def carried_into(self, month):
        """Leftover carried into `month`: 0 before the line's first month."""
        if self.start is None or month <= self.start:
            return 0
        while self.walked < month:
            self.carried[self.walked] = self.carry
            version = self.version_at(self.walked)
            if not version or version["amount_cents"] is None:
                self.carry = 0
            else:
                left = version["amount_cents"] + self.extra.get(self.walked, 0) + self.carry - self.spent.get(self.walked, 0)
                carry = self.choices.get(self.walked, bool(version["rollover"]))
                self.carry = left if carry and left > 0 else 0
            self.walked = next_month(self.walked)
        return self.carry if month == self.walked else self.carried[month]


def budget_lines(conn):
    """Every budget line ({("item" | "category", id): Line}), loaded once per connection
    until its data changes. Lines without any budget history or carry-over choice are left out."""
    def load():
        first = conn.execute("SELECT MIN(substr(date, 1, 7)) AS m FROM expenses").fetchone()["m"]

        def key(row):
            return ("item", row["item_id"]) if row["item_id"] else ("category", row["category_id"])

        versions, spent, extra, choices = {}, {}, {}, {}
        for r in conn.execute("SELECT * FROM budgets ORDER BY start_month"):
            versions.setdefault(key(r), []).append(dict(r))
        for r in conn.execute(
            "SELECT s.category_id, s.item_id, e.kind, substr(e.date, 1, 7) AS month, SUM(s.amount_cents) AS cents "
            "FROM splits s JOIN expenses e ON e.id = s.expense_id GROUP BY 1, 2, 3, 4"
        ):
            target = extra if r["kind"] == "income" else spent
            target.setdefault(key(r), {})[r["month"]] = r["cents"]
        for r in conn.execute("SELECT * FROM rollover_choices"):
            choices.setdefault(key(r), {})[r["month"]] = bool(r["carry"])
        return {k: Line(versions.get(k, []), spent.get(k, {}), extra.get(k, {}), choices.get(k, {}), first)
                for k in versions.keys() | choices.keys()}
    return conn.cached("lines", load)


def categories_for(conn, month):
    """All categories and items with, for `month`: the budget in effect (None = none), the
    leftover carried in, extra budget from income, whether this month's leftover carries
    over, and the budget history."""
    all_lines = budget_lines(conn)

    def line(kind, row):
        found = all_lines.get((kind, row["id"]))
        current = found.version_at(month) if found else None
        active = current is not None and current["amount_cents"] is not None
        default_carry = bool(active and current["rollover"])
        return {
            "id": row["id"],
            "name": row["name"],
            "budget": current["amount_cents"] if active else None,
            "rollover": default_carry,
            "carry": found.choices.get(month, default_carry) if found else default_carry,
            "extra": found.extra.get(month, 0) if active else 0,
            "carried_in": found.carried_into(month) if active else 0,
            "history": [{"id": v["id"], "start_month": v["start_month"], "rollover": bool(v["rollover"]),
                         "amount": v["amount_cents"]} for v in found.versions] if found else [],
        }

    categories = {r["id"]: {**line("category", r), "items": []} for r in conn.execute("SELECT * FROM categories ORDER BY id")}
    for r in conn.execute("SELECT * FROM items ORDER BY id"):
        categories[r["category_id"]]["items"].append(line("item", r))
    return list(categories.values())


def budget_total(conn, month):
    """The month's total budget, without carry-over or extra income: what it's planned to cost."""
    total = 0
    for c in categories_for(conn, month):
        lines = c["items"] if c["items"] else [c]
        total += sum(l["budget"] for l in lines if l["budget"] is not None)
    return total


# ---- Transactions ----

def transactions(conn, month=""):
    """Transactions whose date is in `month` ("" = all), newest first, with their splits."""
    found = {
        r["id"]: {"id": r["id"], "date": r["date"], "amount": r["amount_cents"], "payee": r["payee"],
                  "description": r["description"], "kind": r["kind"], "paid_date": r["paid_date"], "splits": []}
        for r in conn.execute("SELECT * FROM expenses WHERE date LIKE ? ORDER BY date DESC, id DESC", (f"{month}%",))
    }
    for r in conn.execute(
        """
        SELECT s.*, c.name AS category, i.name AS item
        FROM splits s
        JOIN expenses e ON e.id = s.expense_id
        JOIN categories c ON c.id = s.category_id
        LEFT JOIN items i ON i.id = s.item_id
        WHERE e.date LIKE ?
        ORDER BY s.id
        """,
        (f"{month}%",),
    ):
        found[r["expense_id"]]["splits"].append(
            {"category_id": r["category_id"], "item_id": r["item_id"], "category": r["category"],
             "item": r["item"], "amount": r["amount_cents"]}
        )
    return list(found.values())


def split_key(split):
    return f"i{split['item_id']}" if split["item_id"] else f"c{split['category_id']}"


def spent_by_line(items):
    """Expense spending per budget line, and the part outside any budget."""
    spent, outside = {}, 0
    for t in items:
        if t["kind"] != "expense":
            continue
        for s in t["splits"]:
            spent[split_key(s)] = spent.get(split_key(s), 0) + s["amount"]
        outside += t["amount"] - sum(s["amount"] for s in t["splits"])
    return spent, outside


def lines_for(category, spent):
    """The budget lines of a category shown for a month. Categories with items show their
    items; categories without items are a single line. Lines without a budget appear only
    when something was spent on them."""
    def line(prefix, row, name):
        key = f"{prefix}{row['id']}"
        return {"key": key, "name": name, "budget": row["budget"], "carried_in": row["carried_in"],
                "extra": row["extra"], "carry": row["carry"], "spent": spent.get(key, 0)}

    if not category["items"]:
        lines = [line("c", category, None)]
    else:
        lines = [line("i", item, item["name"]) for item in category["items"]]
    lines = [l for l in lines if l["budget"] is not None or l["spent"] > 0]
    unassigned = spent.get(f"c{category['id']}", 0)  # spent on the category before it had items
    if category["items"] and unassigned:
        lines.append({"key": f"c{category['id']}", "name": "Other", "budget": None, "carried_in": 0,
                      "extra": 0, "carry": False, "spent": unassigned})
    for l in lines:
        l["available"] = (l["budget"] or 0) + l["carried_in"] + l["extra"]
    return lines


def month_data(conn, month, exclude=None):
    """Everything about one month: categories, transactions, the budget lines per category
    and the totals. `exclude` leaves out one transaction (the one being edited). Worked out
    once per connection until its data changes, as History and Outlook need the same months
    more than once: don't change the result (copy what you add to)."""
    return conn.cached(("month", month, exclude, current_month()), lambda: _month_data(conn, month, exclude))


def _month_data(conn, month, exclude):
    categories = categories_for(conn, month)
    items = [t for t in transactions(conn, month) if t["id"] != exclude]
    spent, outside = spent_by_line(items)
    groups = []
    for c in categories:
        lines = lines_for(c, spent)
        if lines:
            groups.append({"id": c["id"], "name": c["name"], "has_items": bool(c["items"]), "lines": lines})
    all_lines = [l for g in groups for l in g["lines"]]
    total_spent = sum(t["amount"] for t in items if t["kind"] == "expense")
    moved = lambda kind: sum(t["amount"] for t in items if t["kind"] == kind)
    # Unspent budget that isn't carried over, minus what was already moved to savings.
    unspent = sum(max(0, l["available"] - l["spent"]) for l in all_lines if l["budget"] is not None and not l["carry"])
    saved = moved("save") - moved("withdraw")
    return {
        "month": month,
        "categories": categories,
        "transactions": items,
        "groups": groups,
        "totals": {
            "spent": total_spent,
            "income": moved("income"),
            "budget": sum(l["available"] for l in all_lines),
            "outside": outside,                     # spent outside any budget
            "budget_spent": total_spent - outside,  # spent on budgets
            "carried_in": sum(l["carried_in"] for l in all_lines),
            # Unused budget that goes on to next month.
            "carried_out": sum(max(0, l["available"] - l["spent"]) for l in all_lines if l["budget"] is not None and l["carry"]),
            "net": moved("income") - total_spent,   # income minus spending
        },
        # What's left of the budgets. Until the month ends it can all still be spent, whatever
        # was moved to savings. Afterwards, money moved to savings counts as that leftover;
        # money taken from savings isn't unspent budget, so it never adds to it.
        "leftover": {"unspent": unspent, "saved": saved,
                     "rest": max(0, unspent - max(0, saved)) if month < current_month() else unspent},
    }


def budget_history(conn, year):
    """Looking back on each budget line in `year`: per finished month what was budgeted, what
    was available (with carry-over and extra from income) and what was spent. Per line the
    totals over those months, in how many months the spending went over the budget, and
    whether that's a pattern ("over": usually more spent than budgeted; "under": usually a lot
    left). Lines are grouped by category, with the names they have now. `outside` is the
    same for spending outside any budget (None if there was none)."""
    first = conn.execute("SELECT MIN(substr(date, 1, 7)) AS m FROM expenses").fetchone()["m"]
    months = [f"{year}-{m:02d}" for m in range(1, 13)]
    months = [m for m in months if first and first <= m < current_month()]
    groups, lines = {}, {}
    outside = {"key": "outside", "name": None, "months": {}}  # spent outside any budget: "Uncategorized"
    for month in months:
        data = month_data(conn, month)
        if data["totals"]["outside"]:
            outside["months"][month] = {"budget": None, "available": 0, "spent": data["totals"]["outside"]}
        for g in data["groups"]:
            group = groups.setdefault(g["id"], {"id": g["id"], "lines": []})
            group["name"] = g["name"]
            for l in g["lines"]:
                if l["key"] not in lines:
                    lines[l["key"]] = {"key": l["key"], "months": {}}
                    group["lines"].append(lines[l["key"]])
                lines[l["key"]]["name"] = l["name"]
                lines[l["key"]]["months"][month] = {"budget": l["budget"], "available": l["available"], "spent": l["spent"]}
    for line in [*lines.values(), outside]:
        rows = line["months"].values()
        budgeted = [r for r in rows if r["budget"] is not None]
        line["budget"] = sum(r["budget"] for r in budgeted)
        line["spent"] = sum(r["spent"] for r in rows)
        line["budgeted_months"] = len(budgeted)
        line["over_budget"] = sum(1 for r in budgeted if r["spent"] > r["budget"])  # more than that month's budget
        line["over_available"] = sum(1 for r in budgeted if r["spent"] > r["available"])  # more than there was, carry-over included
        budgeted_spent = sum(r["spent"] for r in budgeted)
        line["pattern"] = None
        if len(budgeted) >= 2 and line["budget"] > 0:
            if line["over_budget"] * 2 >= len(budgeted) and budgeted_spent > line["budget"]:
                line["pattern"] = "over"
            elif line["over_budget"] == 0 and budgeted_spent * 4 < line["budget"] * 3:
                line["pattern"] = "under"  # never over, and on average more than a quarter left
    return {"year": year, "months": months, "groups": [g for g in groups.values() if g["lines"]],
            "outside": outside if outside["months"] else None}
