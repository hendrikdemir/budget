"""Bank and savings balances.

Each account has a starting point (balance at the start of a day, kept in settings).
The expected balance on a day is that starting point plus every transaction since,
counted on the day the money moved (`paid_date`, else `date`). Balance checks record
what the bank showed on a date, to compare with what was expected.
"""
from datetime import date, timedelta

from .money import ApiError, GENERIC_ERROR, today

# How each kind of transaction changes each account's balance.
ACCOUNT_EFFECTS = {
    "bank": {"income": 1, "expense": -1, "save": -1, "withdraw": 1},
    "savings": {"save": 1, "withdraw": -1},
}


def clean_account(value):
    if value not in ACCOUNT_EFFECTS:
        raise ApiError(GENERIC_ERROR)
    return value


def setting(conn, key):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def starting_point(conn, account):
    start, start_date = setting(conn, f"{account}_start_cents"), setting(conn, f"{account}_start_date")
    return (None, None) if start is None or start_date is None else (int(start), start_date)


def expected_balance(conn, account, on_date):
    """Expected balance at the end of `on_date`, or None before/without a starting point."""
    start, start_date = starting_point(conn, account)
    if start is None or on_date < start_date:
        return None
    effect = " ".join(f"WHEN '{kind}' THEN {sign}" for kind, sign in ACCOUNT_EFFECTS[account].items())
    net = conn.execute(
        f"SELECT COALESCE(SUM(amount_cents * CASE kind {effect} ELSE 0 END), 0) AS net "
        "FROM expenses WHERE COALESCE(paid_date, date) >= ? AND COALESCE(paid_date, date) <= ?",
        (start_date, on_date),
    ).fetchone()["net"]
    return start + net


def balance(conn, account):
    """Starting point, expected balance today and the latest checks of an account."""
    start, start_date = starting_point(conn, account)
    checks = []
    for r in conn.execute(
        "SELECT * FROM balance_checks WHERE account = ? ORDER BY date DESC, id DESC LIMIT 10", (account,)
    ):
        expected = expected_balance(conn, account, r["date"])
        checks.append({"id": r["id"], "date": r["date"], "actual": r["amount_cents"], "expected": expected,
                       "difference": None if expected is None else r["amount_cents"] - expected})
    return {"account": account, "start": start, "start_date": start_date,
            "expected": expected_balance(conn, account, today()), "checks": checks}


def year_history(conn, year):
    """Looking back on `year`: per finished month the income, spending and their difference,
    and the expected bank and savings balance at its end (None before that account's tracking
    started). Months before the first starting point are left out, as nothing was kept then
    (without a starting point: months before the first transaction). `empty` says there's
    nothing at all to look back on yet: no starting point and no transaction. The
    month you're in isn't included: until it's over, its result says little (the income may
    not be in yet). Plus the totals of those months and which years have data."""
    from .budgets import month_data  # budgets doesn't need accounts, so no import cycle
    now = today()
    starts = [d for d in (starting_point(conn, a)[1] for a in ACCOUNT_EFFECTS) if d]
    first = conn.execute("SELECT MIN(substr(date, 1, 7)) AS m FROM expenses").fetchone()["m"]
    begin = min(starts)[:7] if starts else first  # None: nothing has been added yet
    months = []
    for m in range(1, 13):
        month = f"{year}-{m:02d}"
        if month >= now[:7]:
            break
        if not begin or month < begin:
            continue
        end = (date(year + m // 12, m % 12 + 1, 1) - timedelta(days=1)).isoformat()
        totals = month_data(conn, month)["totals"]
        months.append({"month": month, "income": totals["income"], "spent": totals["spent"], "net": totals["net"],
                       "bank": expected_balance(conn, "bank", end), "savings": expected_balance(conn, "savings", end)})

    def at_start(account):
        """The balance as the year began: last year's end, or the starting point if tracking began this year."""
        start, start_date = starting_point(conn, account)
        if start is None or start_date[:4] > str(year):
            return None
        return start if start_date[:4] == str(year) else expected_balance(conn, account, f"{year - 1}-12-31")

    def change(account):
        first, last = at_start(account), next((m[account] for m in reversed(months) if m[account] is not None), None)
        return None if first is None or last is None else last - first

    return {
        "year": year, "months": months, "empty": not begin,
        "first_year": int((begin or now)[:4]), "last_year": int(now[:4]),
        "totals": {"income": sum(m["income"] for m in months), "spent": sum(m["spent"] for m in months),
                   "net": sum(m["net"] for m in months), "bank_change": change("bank"), "savings_change": change("savings")},
    }
