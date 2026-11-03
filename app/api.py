"""HTTP API handlers. Each takes (conn, id, body, query) and returns JSON-able data.
Amounts in requests and responses are whole cents."""
import re

from . import VERSION, accounts, backup, bank_import, budgets, outlook
from .budgets import end_budget, has_history_before, is_active, set_budget, target_column, version_at
from .money import ApiError, GENERIC_ERROR, cents, clean_date, clean_month, clean_name, current_month

DEFAULT_SETTINGS = {"theme": "system", "currency": "EUR"}


def first(query, name, default=""):
    return query.get(name, [default])[0]


# ---- Months and transactions ----

def get_month(conn, _, __, query):
    """Everything the overview shows for a month, including whether it's ready for the next."""
    month = clean_month(first(query, "month", current_month()))
    exclude = int(first(query, "exclude")) if first(query, "exclude") else None
    data = budgets.month_data(conn, month, exclude)
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
        raise ApiError("Enter who paid you." if kind == "income" else "Enter who you paid.")
    amount = cents(body.get("amount"))
    splits = []
    for split in [] if transfer else body.get("splits") or []:
        item_id = split.get("item_id") or None
        if item_id:
            row = conn.execute("SELECT category_id FROM items WHERE id = ?", (item_id,)).fetchone()
        else:
            row = conn.execute("SELECT id AS category_id FROM categories WHERE id = ?", (split.get("category_id"),)).fetchone()
        if not row:
            raise ApiError("That budget doesn't exist anymore. Choose one from the list, or leave it empty.")
        splits.append((row["category_id"], item_id, cents(split.get("amount"))))
    if sum(s[2] for s in splits) > amount:
        raise ApiError("The budget parts add up to more than the total amount. Lower one of the parts.")
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
    """Add the reviewed transactions, all or none. Each may name one budget line for its full amount."""
    items = body.get("transactions") or []
    for t in items:
        line = t.get("line") or ""
        splits = []
        if re.fullmatch(r"[ic]\d+", line) and t.get("kind") in ("expense", "income"):
            splits = [{"item_id" if line[0] == "i" else "category_id": int(line[1:]), "amount": t.get("amount")}]
        try:
            save_transaction(conn, None, {**t, "splits": splits}, None)
        except ApiError as e:
            raise ApiError(f"{t.get('payee') or 'The savings transfer'} on {t.get('date')}: {e} Nothing was added yet.")
    return {"added": len(items)}


# ---- Categories, items and budgets ----

def create_category(conn, _, body, __):
    name, month = clean_name(body.get("name")), clean_month(body.get("month"))
    amount = cents(body.get("budget", 0), allow_zero=True)
    existing = conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
    if existing:
        # Bring back a removed category, keeping its history.
        cat_id = existing["id"]
        item_ids = [r["id"] for r in conn.execute("SELECT id FROM items WHERE category_id = ?", (cat_id,))]
        lines = [("item_id", i) for i in item_ids] or [("category_id", cat_id)]
        if any(is_active(conn, col, i, month) for col, i in lines):
            raise ApiError(f"You already have a category called “{name}”.")
    else:
        cat_id = conn.execute("INSERT INTO categories (name) VALUES (?)", (name,)).lastrowid
    set_budget(conn, "category_id", cat_id, month, amount)
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
            raise ApiError(f"“{name}” already exists in this category.")
        item_id = existing["id"]
    else:
        item_id = conn.execute("INSERT INTO items (category_id, name) VALUES (?, ?)", (category_id, name)).lastrowid
    set_budget(conn, "item_id", item_id, month, amount)
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
    return accounts.year_history(conn, int(first(query, "year")))


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


def save_plan(conn, plan_id, body, _):
    kind = body.get("kind") if body.get("kind") in ("income", "expense") else None
    if not kind:
        raise ApiError(GENERIC_ERROR)
    start = clean_month(body.get("start_month"))
    end = clean_month(body["end_month"]) if body.get("end_month") else None
    if end and end < start:
        raise ApiError("The end month is before the start month. Choose a later end month.")
    values = (kind, clean_name(body.get("name")), cents(body.get("amount")), start, end)
    if plan_id is None:
        conn.execute("INSERT INTO plans (kind, name, amount_cents, start_month, end_month) VALUES (?, ?, ?, ?, ?)", values)
    else:
        conn.execute("UPDATE plans SET kind = ?, name = ?, amount_cents = ?, start_month = ?, end_month = ? WHERE id = ?",
                     (*values, plan_id))
    return {"ok": True}


def delete_plan(conn, plan_id, _, __):
    conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
    return {"ok": True}


def add_plan_change(conn, _, body, __):
    plan = conn.execute("SELECT * FROM plans WHERE id = ?", (body.get("plan_id"),)).fetchone()
    if not plan:
        raise ApiError("This plan no longer exists. Reload the page and try again.")
    month = clean_month(body.get("start_month"))
    if month <= plan["start_month"]:
        raise ApiError("Choose a month after the plan starts.")
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
            raise ApiError("Enter a number of months, like 1,5.")
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


def undo_import(conn, _, __, ___):
    return backup.undo()


def import_status(conn, _, __, ___):
    return backup.status()


# ---- Settings ----

def get_version(conn, _, __, ___):
    return {"version": VERSION}



def get_settings(conn, _, __, ___):
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {**DEFAULT_SETTINGS, **{r["key"]: r["value"] for r in rows if r["key"] in DEFAULT_SETTINGS}}


def save_settings(conn, _, body, __):
    data = {k: str(v) for k, v in body.items() if k in DEFAULT_SETTINGS}
    if "currency" in data and not re.fullmatch(r"[A-Z]{3}", data["currency"]):
        raise ApiError("Choose a currency from the list.")
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
    ("POST", "backup-undo", False): undo_import,
    ("GET", "backup-status", False): import_status,
    ("GET", "version", False): get_version,
    ("GET", "settings", False): get_settings,
    ("POST", "settings", False): save_settings,
}
