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


def history(conn, account, year):
    """Expected balance at the end of each month of `year` (today for the current
    month; nothing for future months)."""
    now = today()
    months = []
    for m in range(1, 13):
        first = date(year, m, 1)
        if first.isoformat() > now:
            break
        end = (date(year + m // 12, m % 12 + 1, 1) - timedelta(days=1)).isoformat()
        months.append({"month": first.isoformat()[:7], "balance": expected_balance(conn, account, min(end, now))})
    return {"account": account, "year": year, "months": months}
