"""HTTP API handlers. Each takes (conn, id, body, query) and returns JSON-able data.
Amounts in requests and responses are whole cents."""
import re

from . import VERSION, accounts, i18n, backup, bank_import, budgets, export, outlook, updates
from .budgets import end_budget, has_history_before, is_active, set_budget, target_column, version_at
from .money import ApiError, GENERIC_ERROR, cents, clean_date, clean_month, clean_name, current_month, previous_month

# number_format: "comma" (1.234,56), "point" (1,234.56) or "system" (the way this computer writes numbers).
# language: "system" (as this computer) or a code from i18n.LANGUAGES. mode: "simple" shows the
# basics, "full" every feature (new data starts simple; data from before modes existed is full,
# see db._v3_mode). offers_dismissed: the offers of features put away with Not now, "a,b".
DEFAULT_SETTINGS = {"theme": "system", "currency": "EUR", "number_format": "system", "update_check": "on", "skipped_version": "",
                    "guide": "show",  # the getting-started guide on the overview: "show" or "hidden"
                    "language": "system", "mode": "simple", "offers_dismissed": ""}
OFFERS = ("bank", "outlook", "carry", "savings")


def first(query, name, default=""):
    return query.get(name, [default])[0]


# ---- Months and transactions ----

def get_month(conn, _, __, query):
    """Everything the overview shows for a month, including whether it's ready for the next."""
    month = clean_month(first(query, "month", current_month()))
    exclude = int(first(query, "exclude")) if first(query, "exclude") else None
    data = {**budgets.month_data(conn, month, exclude)}  # a copy: month_data's result is shared
    data["outlook"] = outlook.month_outlook(conn, month, data)
    return data


def list_transactions(conn, _, __, query):
    return budgets.transactions(conn, first(query, "month"))


def save_transaction(conn, transaction_id, body, _):
    """Create (no id) or replace an expense, income or savings transfer. Splits may cover
    only part of the amount, or none of it: the rest is uncategorized (or unallocated income)."""
    kind = body.get("kind") if body.get("kind") in ("income", "save", "withdraw") else "expense"
    transfer = kind in ("save", "withdraw")
    day = clean_date(body.get("date"))
    payee = "" if transfer else str(body.get("payee", "")).strip()
    if not payee and not transfer:
        raise ApiError("errors.payerMissing" if kind == "income" else "errors.payeeMissing")
    amount = cents(body.get("amount"))
    splits = []
    for split in [] if transfer else body.get("splits") or []:
        item_id = split.get("item_id") or None
        if item_id:
            row = conn.execute("SELECT category_id FROM items WHERE id = ?", (item_id,)).fetchone()
        else:
            row = conn.execute("SELECT id AS category_id FROM categories WHERE id = ?", (split.get("category_id"),)).fetchone()
        if not row:
            raise ApiError("errors.budgetGone")
        splits.append((row["category_id"], item_id, cents(split.get("amount"))))
    if sum(s[2] for s in splits) > amount:
        raise ApiError("errors.splitsTooHigh")
    paid_date = clean_date(body["paid_date"]) if body.get("paid_date") else None
    if paid_date == day:
        paid_date = None
    values = (day, amount, payee, str(body.get("description", "")).strip(), kind, paid_date)
    if transaction_id is None:
        transaction_id = conn.execute(
            "INSERT INTO expenses (date, amount_cents, payee, description, kind, paid_date) VALUES (?, ?, ?, ?, ?, ?)", values
        ).lastrowid
    else:
        conn.execute(
            "UPDATE expenses SET date = ?, amount_cents = ?, payee = ?, description = ?, kind = ?, paid_date = ? WHERE id = ?",
            (*values, transaction_id),
        )
        conn.execute("DELETE FROM splits WHERE expense_id = ?", (transaction_id,))
    conn.executemany(
        "INSERT INTO splits (expense_id, category_id, item_id, amount_cents) VALUES (?, ?, ?, ?)",
        [(transaction_id, *s) for s in splits],
    )
    return {"ok": True}


def delete_transaction(conn, transaction_id, _, __):
    conn.execute("DELETE FROM expenses WHERE id = ?", (transaction_id,))
    return {"ok": True}


def delete_transactions(conn, _, body, __):
    ids = [int(i) for i in body.get("ids", [])]
    conn.executemany("DELETE FROM expenses WHERE id = ?", [(i,) for i in ids])
    return {"deleted": len(ids)}


def list_payees(conn, _, __, ___):
    """Known payees (and payers, for income), most recent first, with the budget line last used for each."""
    payees = {}
    for r in conn.execute(
        "SELECT e.payee, e.kind, s.category_id, s.item_id FROM expenses e LEFT JOIN splits s ON s.expense_id = e.id "
        "WHERE e.payee != '' ORDER BY e.date DESC, e.id DESC, s.id"
    ):
        line = f"i{r['item_id']}" if r["item_id"] else f"c{r['category_id']}" if r["category_id"] else None
        payees.setdefault((r["payee"], r["kind"]), line)
    return [{"name": name, "kind": kind, "line": line} for (name, kind), line in payees.items()]


# ---- Importing from a bank ----

def bank_import_preview(conn, _, body, __):
    """The transactions in an exported bank file, with suggestions, to review. Nothing is added yet."""
    return bank_import.preview(conn, body, list_payees(conn, None, None, None))


def bank_import_add(conn, _, body, __):
    """Add the reviewed transactions, all or none. Each may name one budget line for its full
    amount, or `splits`: [{line, amount}]."""
    items = body.get("transactions") or []
    for t in items:
        # One budget line for the full amount, or (from a Budget export) the parts of a split.
        parts = t.get("splits") or [{"line": t.get("line") or "", "amount": t.get("amount")}]
        splits = [{"item_id" if p["line"][0] == "i" else "category_id": int(p["line"][1:]), "amount": p.get("amount")}
                  for p in parts if re.fullmatch(r"[ic]\d+", str(p.get("line") or "")) and t.get("kind") in ("expense", "income")]
        try:
            save_transaction(conn, None, {**t, "splits": splits}, None)
        except ApiError as e:
            if t.get("payee"):
                raise ApiError("errors.importFailed", payee=t["payee"], date=t.get("date"), error=e)
            raise ApiError("errors.importTransferFailed", date=t.get("date"), error=e)
    return {"added": len(items)}


# ---- Categories, items and budgets ----

def create_category(conn, _, body, __):
    """A new category with its budget from `month`; `rollover` carries its leftovers over by default."""
    name, month = clean_name(body.get("name")), clean_month(body.get("month"))
    amount = cents(body.get("budget", 0), allow_zero=True)
    existing = conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
    if existing:
        # Bring back a removed category, keeping its history.
        cat_id = existing["id"]
        item_ids = [r["id"] for r in conn.execute("SELECT id FROM items WHERE category_id = ?", (cat_id,))]
        lines = [("item_id", i) for i in item_ids] or [("category_id", cat_id)]
        if any(is_active(conn, col, i, month) for col, i in lines):
            raise ApiError("errors.categoryExists", name=name)
    else:
        cat_id = conn.execute("INSERT INTO categories (name) VALUES (?)", (name,)).lastrowid
    set_budget(conn, "category_id", cat_id, month, amount, bool(body.get("rollover")))
    return {"ok": True}


def rename_category(conn, cat_id, body, _):
    conn.execute("UPDATE categories SET name = ? WHERE id = ?", (clean_name(body.get("name")), cat_id))
    return {"ok": True}


def remove_category(conn, cat_id, _, query):
    """Delete a category that was never used; otherwise end it (and its items) from `month`."""
    month = clean_month(first(query, "month"))
    item_ids = [r["id"] for r in conn.execute("SELECT id FROM items WHERE category_id = ?", (cat_id,))]
    used = conn.execute("SELECT 1 FROM splits WHERE category_id = ?", (cat_id,)).fetchone() or \
        has_history_before(conn, "category_id", cat_id, month) or \
        any(has_history_before(conn, "item_id", i, month) for i in item_ids)
    if not used:
        conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        return {"deleted": True}
    end_budget(conn, "category_id", cat_id, month)
    for item_id in item_ids:
        end_budget(conn, "item_id", item_id, month)
    return {"ended": True}


def create_item(conn, _, body, __):
    name, month = clean_name(body.get("name")), clean_month(body.get("month"))
    amount = cents(body.get("budget", 0), allow_zero=True)
    category_id = body.get("category_id")
    existing = conn.execute("SELECT id FROM items WHERE category_id = ? AND name = ?", (category_id, name)).fetchone()
    if existing:
        # Bring back a removed item, keeping its history.
        if is_active(conn, "item_id", existing["id"], month):
            raise ApiError("errors.itemExists", name=name)
        item_id = existing["id"]
    else:
        item_id = conn.execute("INSERT INTO items (category_id, name) VALUES (?, ?)", (category_id, name)).lastrowid
    set_budget(conn, "item_id", item_id, month, amount, bool(body.get("rollover")))
    return {"ok": True}


def rename_item(conn, item_id, body, _):
    conn.execute("UPDATE items SET name = ? WHERE id = ?", (clean_name(body.get("name")), item_id))
    return {"ok": True}


def remove_item(conn, item_id, _, query):
    """Delete an item that was never used; otherwise end its budget from `month`."""
    month = clean_month(first(query, "month"))
    used = conn.execute("SELECT 1 FROM splits WHERE item_id = ?", (item_id,)).fetchone() or \
        has_history_before(conn, "item_id", item_id, month)
    if not used:
        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        return {"deleted": True}
    end_budget(conn, "item_id", item_id, month)
    return {"ended": True}


def change_budget(conn, _, body, __):
    column, target_id = target_column(body)
    rollover = body.get("rollover")
    set_budget(conn, column, target_id, clean_month(body.get("month")),
               cents(body.get("amount"), allow_zero=True), None if rollover is None else bool(rollover))
    return {"ok": True}


def delete_budget_change(conn, budget_id, _, __):
    conn.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
    return {"ok": True}


def choose_rollover(conn, _, body, __):
    """Decide for one month whether its leftover carries over, overriding the default."""
    column, target_id = target_column(body)
    month = clean_month(body.get("month"))
    carry = bool(body.get("carry"))
    conn.execute(f"DELETE FROM rollover_choices WHERE {column} = ? AND month = ?", (target_id, month))
    version = version_at(conn, column, target_id, month)
    if carry != bool(version and version["rollover"]):
        conn.execute(f"INSERT INTO rollover_choices ({column}, month, carry) VALUES (?, ?, ?)", (target_id, month, int(carry)))
    return {"ok": True}


# ---- Accounts ----

def get_balance(conn, _, __, query):
    return accounts.balance(conn, accounts.clean_account(first(query, "account", "bank")))


def year_history(conn, _, __, query):
    year = int(first(query, "year"))
    return {**accounts.year_history(conn, year), "budgets": budgets.budget_history(conn, year)}


def transactions_csv(conn, _, __, query):
    """A CSV of the transactions in a month ("" = all), or of those in `ids` ("1,2,3")."""
    month, ids = first(query, "month"), first(query, "ids")
    if ids and not re.fullmatch(r"\d+(,\d+)*", ids):
        raise ApiError(GENERIC_ERROR)
    chosen = {int(i) for i in ids.split(",")} if ids else None
    return export.transactions_csv(conn, clean_month(month) if month else "", first(query, "decimal", "."), chosen)


def set_balance_start(conn, _, body, __):
    account = accounts.clean_account(body.get("account", "bank"))
    values = {f"{account}_start_cents": str(cents(body.get("amount"), signed=True)),
              f"{account}_start_date": clean_date(body.get("date"))}
    conn.executemany(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        values.items(),
    )
    return {"ok": True}


def add_balance_check(conn, _, body, __):
    conn.execute(
        "INSERT INTO balance_checks (account, date, amount_cents) VALUES (?, ?, ?)",
        (accounts.clean_account(body.get("account", "bank")), clean_date(body.get("date")), cents(body.get("amount"), signed=True)),
    )
    return {"ok": True}


def delete_balance_check(conn, check_id, _, __):
    conn.execute("DELETE FROM balance_checks WHERE id = ?", (check_id,))
    return {"ok": True}


# ---- Plans and projection ----

def list_plans(conn, _, __, ___):
    return outlook.plans(conn)


def income_total(conn, _, __, ___):
    return outlook.income_total(conn)


def save_plan(conn, plan_id, body, _):
    kind = body.get("kind") if body.get("kind") in ("income", "expense") else None
    if not kind:
        raise ApiError(GENERIC_ERROR)
    start = clean_month(body.get("start_month"))
    end = clean_month(body["end_month"]) if body.get("end_month") else None
    if end and end < start:
        raise ApiError("errors.endBeforeStart")
    every = body.get("every_months", 1)
    if not isinstance(every, int) or not 1 <= every <= 12:
        raise ApiError("errors.repeatRange")
    values = (kind, clean_name(body.get("name")), cents(body.get("amount")), start, end, 1 if end == start else every)
    if plan_id is None:
        conn.execute("INSERT INTO plans (kind, name, amount_cents, start_month, end_month, every_months) VALUES (?, ?, ?, ?, ?, ?)", values)
    else:
        conn.execute("UPDATE plans SET kind = ?, name = ?, amount_cents = ?, start_month = ?, end_month = ?, every_months = ? WHERE id = ?",
                     (*values, plan_id))
    if values[-1] > 1:  # a plan every few months has one amount: no changes over time
        conn.execute("DELETE FROM plan_changes WHERE plan_id = ?", (plan_id,))
    return {"ok": True}


def delete_plan(conn, plan_id, _, __):
    conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
    return {"ok": True}


def add_plan_change(conn, _, body, __):
    plan = conn.execute("SELECT * FROM plans WHERE id = ?", (body.get("plan_id"),)).fetchone()
    if not plan:
        raise ApiError("errors.planGone")
    month = clean_month(body.get("start_month"))
    if plan["every_months"] > 1:
        raise ApiError("errors.customPlanOneAmount")
    if month <= plan["start_month"]:
        raise ApiError("errors.changeAfterStart")
    conn.execute("DELETE FROM plan_changes WHERE plan_id = ? AND start_month = ?", (plan["id"], month))
    conn.execute("INSERT INTO plan_changes (plan_id, start_month, amount_cents) VALUES (?, ?, ?)",
                 (plan["id"], month, cents(body.get("amount"))))
    return {"ok": True}


def delete_plan_change(conn, change_id, _, __):
    conn.execute("DELETE FROM plan_changes WHERE id = ?", (change_id,))
    return {"ok": True}


def get_projection(conn, _, __, ___):
    return outlook.projection(conn)


def set_buffer(conn, _, body, __):
    """The savings buffer: a number of months of budget, or a fixed amount."""
    if body.get("mode") == "amount":
        values = {"buffer_mode": "amount", "buffer_amount": str(cents(body.get("amount"), allow_zero=True))}
    else:
        months = body.get("months")
        if isinstance(months, bool) or not isinstance(months, (int, float)) or not 0 <= months <= 120:
            raise ApiError("errors.bufferMonths")
        values = {"buffer_mode": "months", "buffer_months": str(months)}
    conn.executemany(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        values.items(),
    )
    return {"ok": True}


# ---- Export and import ----

def export_data(conn, _, __, ___):
    return backup.export_file()  # a (file name, contents) pair: sent as a download


def check_backup(conn, _, body, __):
    return backup.check(body)


def restore_backup(conn, _, body, __):
    return backup.restore(body)


def list_auto_backups(conn, _, __, ___):
    return backup.auto_backups()


def check_auto_backup(conn, _, body, __):
    return backup.check_auto(body.get("name"))


def restore_auto_backup(conn, _, body, __):
    return backup.restore_auto(body.get("name"))


def clear_data(conn, _, body, __):
    """Deletes all data. The page must say it means it: after an export, or with exporting skipped."""
    if body.get("confirm") is not True:
        raise ApiError(GENERIC_ERROR)
    return backup.clear()


# ---- Getting started ----

def get_setup(conn, _, __, ___):
    """What's been set up so far, for the getting-started guide on the overview: a starting
    balance per account, a budget, a transaction and an expected income. `hidden` once the
    user put the guide away. `offers`: features that would be useful now (see offers())."""
    has = lambda sql: conn.execute(sql).fetchone() is not None
    settings = get_settings(conn, None, None, None)
    steps = {
        "bank": accounts.starting_point(conn, "bank")[0] is not None,
        "savings": accounts.starting_point(conn, "savings")[0] is not None,
        "budgets": has("SELECT 1 FROM budgets WHERE amount_cents > 0"),
        "transaction": has("SELECT 1 FROM expenses"),
        "income": has("SELECT 1 FROM plans WHERE kind = 'income'"),
    }
    return {"steps": steps, "hidden": settings["guide"] == "hidden", "offers": offers(conn, settings, steps)}


def offers(conn, settings, steps):
    """Features to offer now, most useful first, while only the basics are shown (mode simple):
    each when its moment has come, and not after the user put it away with Not now.
    - bank: Budget has been kept for two weeks, or income was added, but the bank balance isn't
      tracked: keeping it shows when a transaction is missing (and the Outlook needs it).
    - outlook: a month has been kept and the bank balance is known, so "Ready for next month?"
      and the Outlook can say something.
    - carry: a budget had money left in each of the last two months (the one most left), so
      carrying it over to the next month may suit it.
    - savings: money was moved to or from savings, but the savings balance isn't tracked.
    """
    dismissed = set(settings["offers_dismissed"].split(","))
    month = current_month()
    found = []
    if settings["mode"] == "simple":
        span = conn.execute("SELECT julianday(MAX(date)) - julianday(MIN(date)) AS days FROM expenses").fetchone()["days"]
        if not steps["bank"] and ((span or 0) >= 14 or conn.execute("SELECT 1 FROM expenses WHERE kind = 'income'").fetchone()):
            found.append({"id": "bank"})
        if steps["bank"] and conn.execute("SELECT 1 FROM expenses WHERE date < ?", (f"{month}-01",)).fetchone():
            found.append({"id": "outlook"})
        last = previous_month(month)
        before = previous_month(last)
        if conn.execute("SELECT 1 FROM expenses WHERE date >= ? AND date < ?", (f"{before}-01", f"{month}-01")).fetchone():
            left = {}
            for m in (before, last):
                for g in budgets.month_data(conn, m)["groups"]:
                    for l in g["lines"]:
                        if l["budget"] and not l["carry"] and l["spent"] < l["available"]:
                            name = f"{g['name']} · {l['name']}" if g["has_items"] else g["name"]
                            left.setdefault(l["key"], []).append((name, l["available"] - l["spent"]))
            both = [v for v in left.values() if len(v) == 2]
            if both:
                best = max(both, key=lambda v: v[0][1] + v[1][1])
                found.append({"id": "carry", "name": best[1][0], "months": [before, last]})
    if not steps["savings"] and conn.execute("SELECT 1 FROM expenses WHERE kind IN ('save', 'withdraw')").fetchone():
        found.append({"id": "savings"})
    return [o for o in found if o["id"] not in dismissed]


# ---- Setting up budgets ----

def budget_fit(conn, _, __, query):
    """Whether the budgets fit the income, for the budget editor: the month's expected income
    (from the income plans), its budgets (without carry-over), its planned extra costs, and
    what's left of the income after both. `plan` is the income plan to change when there's
    just one, repeating monthly; `spending` the average spent per month over the last three
    months with transactions, to help choose amounts."""
    month = clean_month(first(query, "month", current_month()))
    all_plans = outlook.plans(conn)
    income = outlook.planned_in(all_plans, "income", month)
    planned = outlook.planned_in(all_plans, "expense", month)
    total = budgets.budget_total(conn, month)
    income_plans = [p for p in all_plans if p["kind"] == "income" and outlook.falls_in(p, month)]
    plan = income_plans[0] if len(income_plans) == 1 and income_plans[0]["every_months"] == 1 \
        and income_plans[0]["end_month"] != income_plans[0]["start_month"] else None
    months = [r["m"] for r in conn.execute(
        "SELECT DISTINCT substr(date, 1, 7) AS m FROM expenses WHERE kind = 'expense' AND date < ? ORDER BY m DESC LIMIT 3",
        (f"{month}-01",))]
    spending = None
    if months:
        spent = sum(budgets.month_data(conn, m)["totals"]["spent"] for m in months)
        spending = {"months": len(months), "average": spent // len(months)}
    return {"month": month, "income": income, "budgets": total, "planned": planned, "left": income - total - planned,
            "income_plans": len(income_plans), "plan": plan and {"id": plan["id"]}, "spending": spending}


def set_income(conn, _, body, __):
    """The monthly income from the budget editor: a new monthly income plan from `month` when
    there is none yet, or a new amount for the one there is, from `month` on (earlier months
    keep theirs)."""
    month, amount = clean_month(body.get("month")), cents(body.get("amount"))
    plan_id = body.get("plan_id")
    if plan_id is None:
        conn.execute("INSERT INTO plans (kind, name, amount_cents, start_month, end_month, every_months) VALUES ('income', ?, ?, ?, NULL, 1)",
                     (clean_name(body.get("name")), amount, month))
        return {"ok": True}
    plan = conn.execute("SELECT * FROM plans WHERE id = ? AND kind = 'income'", (plan_id,)).fetchone()
    if not plan:
        raise ApiError("errors.planGone")
    if month <= plan["start_month"]:
        conn.execute("UPDATE plans SET amount_cents = ?, start_month = ? WHERE id = ?", (amount, month, plan_id))
        conn.execute("DELETE FROM plan_changes WHERE plan_id = ?", (plan_id,))
    else:
        conn.execute("DELETE FROM plan_changes WHERE plan_id = ? AND start_month >= ?", (plan_id, month))
        conn.execute("INSERT INTO plan_changes (plan_id, start_month, amount_cents) VALUES (?, ?, ?)", (plan_id, month, amount))
    return {"ok": True}


def add_starter_budgets(conn, _, body, __):
    """Several budgets at once, from the suggestions for a new user, from `month`: categories
    with one budget, {name, budget}, or with items, {name, items: [{name, budget}]}. All or
    none: one that can't be added (a name already in use) adds nothing."""
    month = clean_month(body.get("month"))
    chosen = [b for b in body.get("budgets") or [] if "items" not in b or b["items"]]
    if not chosen:
        raise ApiError("errors.noStarterBudgets")
    for b in chosen:
        name = clean_name(b.get("name"))
        create_category(conn, None, {"name": name, "budget": 0 if "items" in b else b.get("budget"), "month": month}, None)
        category_id = conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()["id"]
        for item in b.get("items") or []:
            create_item(conn, None, {"category_id": category_id, "name": item.get("name"), "budget": item.get("budget"), "month": month}, None)
    return {"added": sum(len(b.get("items") or [1]) for b in chosen)}


# ---- Settings ----

def get_version(conn, _, __, ___):
    return {"version": VERSION}


def check_update(conn, _, __, ___):
    """Whether a newer Budget is available on GitHub (see app/updates.py)."""
    settings = get_settings(conn, None, None, None)
    return updates.check(settings["update_check"] == "on", settings["skipped_version"])


def get_settings(conn, _, __, ___):
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {**DEFAULT_SETTINGS, **{r["key"]: r["value"] for r in rows if r["key"] in DEFAULT_SETTINGS}}


def save_settings(conn, _, body, __):
    data = {k: str(v) for k, v in body.items() if k in DEFAULT_SETTINGS}
    if "currency" in data and not re.fullmatch(r"[A-Z]{3}", data["currency"]):
        raise ApiError("errors.chooseCurrency")
    if data.get("update_check", "on") not in ("on", "off") or len(data.get("skipped_version", "")) > 20 \
            or data.get("number_format", "system") not in ("system", "comma", "point") \
            or data.get("guide", "show") not in ("show", "hidden") \
            or data.get("language", "system") not in ("system", *i18n.LANGUAGES) \
            or data.get("mode", "simple") not in ("simple", "full") \
            or not set(filter(None, data.get("offers_dismissed", "").split(","))) <= set(OFFERS):
        raise ApiError(GENERIC_ERROR)
    conn.executemany(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        data.items(),
    )
    return {"ok": True}


# (method, resource, has_id) -> handler
ROUTES = {
    ("GET", "month", False): get_month,
    ("GET", "transactions", False): list_transactions,
    ("POST", "transactions", False): save_transaction,
    ("PUT", "transactions", True): save_transaction,
    ("DELETE", "transactions", True): delete_transaction,
    ("POST", "transactions-delete", False): delete_transactions,
    ("GET", "transactions-csv", False): transactions_csv,
    ("GET", "payees", False): list_payees,
    ("POST", "bank-import-preview", False): bank_import_preview,
    ("POST", "bank-import", False): bank_import_add,
    ("POST", "categories", False): create_category,
    ("PUT", "categories", True): rename_category,
    ("DELETE", "categories", True): remove_category,
    ("POST", "items", False): create_item,
    ("PUT", "items", True): rename_item,
    ("DELETE", "items", True): remove_item,
    ("PUT", "budgets", False): change_budget,
    ("DELETE", "budgets", True): delete_budget_change,
    ("PUT", "rollover", False): choose_rollover,
    ("GET", "balance", False): get_balance,
    ("PUT", "balance", False): set_balance_start,
    ("GET", "history", False): year_history,
    ("POST", "balance-checks", False): add_balance_check,
    ("DELETE", "balance-checks", True): delete_balance_check,
    ("GET", "plans", False): list_plans,
    ("GET", "income-total", False): income_total,
    ("POST", "plans", False): save_plan,
    ("PUT", "plans", True): save_plan,
    ("DELETE", "plans", True): delete_plan,
    ("POST", "plan-changes", False): add_plan_change,
    ("DELETE", "plan-changes", True): delete_plan_change,
    ("GET", "projection", False): get_projection,
    ("PUT", "buffer", False): set_buffer,
    ("GET", "export", False): export_data,
    ("POST", "backup-check", False): check_backup,
    ("POST", "backup-restore", False): restore_backup,
    ("GET", "auto-backups", False): list_auto_backups,
    ("POST", "auto-backup-check", False): check_auto_backup,
    ("POST", "auto-backup-restore", False): restore_auto_backup,
    ("POST", "clear-data", False): clear_data,
    ("GET", "setup", False): get_setup,
    ("GET", "budget-fit", False): budget_fit,
    ("PUT", "income", False): set_income,
    ("POST", "starter-budgets", False): add_starter_budgets,
    ("GET", "version", False): get_version,
    ("GET", "update", False): check_update,
    ("GET", "settings", False): get_settings,
    ("POST", "settings", False): save_settings,
}
