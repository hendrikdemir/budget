"""Looking ahead: is there enough for next month, and how will savings develop?

Next month's budget (minus what's already paid in advance) should be in the bank on the
1st. Unspent budget that isn't carried over covers next month first; only what next
month doesn't need is savings. A shortfall beyond that has to come from savings. During
a month, the income its plans still expect counts too: it isn't in the bank yet, so a
shortfall is only a forecast until the income is in. The overview only brings it up in a
month's last week; before that it's too early to say.

The projection starts from all money in the bank and savings today plus the income still
expected this month (assuming the rest of this month's budget is spent). Each coming month adds expected income (plans) and
subtracts its budgets and planned expenses. Expected savings = the savings once the month is
settled: what's left in the bank after next month's budget is set aside goes to savings (or a
shortfall comes from it). Free to spend = what's above the buffer in that month and every later
one; needed later = what's above the buffer now but needed for a dip in a later month. The buffer is a number of months of budget, or a fixed amount.
"""
from datetime import date, timedelta

from .accounts import expected_balance, setting, starting_point
from .budgets import budget_total, month_data
from .money import current_month, month_end, next_month, today

HORIZON = 12  # months ahead
READY_DAYS = 7  # the overview asks "ready for next month?" in a month's last week


def prepaid(data):
    """Budgeted spending of a month that already left the bank before the month began."""
    first = f"{data['month']}-01"
    return sum(sum(s["amount"] for s in t["splits"]) for t in data["transactions"]
               if t["kind"] == "expense" and t["paid_date"] and t["paid_date"] < first)


def next_month_needs(conn, month):
    """What the month after `month` needs in the bank on its 1st."""
    data = month_data(conn, next_month(month))
    budget = sum((l["budget"] or 0) + l["carried_in"] for g in data["groups"] for l in g["lines"])
    paid = prepaid(data)
    return {"budget": budget, "prepaid": paid, "needed": budget - paid}


def income_to_come(conn, month, data):
    """Income a month's plans still expect, beyond what `data` (from month_data) already has."""
    return max(0, planned_in(plans(conn), "income", month) - data["totals"]["income"])


def month_outlook(conn, month, data):
    """Whether the bank will hold next month's budget on the 1st, for `month` with its
    `data` (from month_data)."""
    now = current_month()
    when = "past" if month < now else "current" if month == now else "future"
    rest = data["leftover"]["rest"]
    last_week = date.fromisoformat(month_end(month)) - timedelta(days=READY_DAYS - 1)
    result = {"month": month, "next": next_month(month), "end": month_end(month), "when": when,
              "too_early": when == "current" and today() < last_week.isoformat(),
              **data["leftover"], **next_month_needs(conn, month), "balance": None}
    if when == "future":
        return result
    balance = expected_balance(conn, "bank", month_end(month) if when == "past" else today())
    if balance is None:
        return result
    expected = income_to_come(conn, month, data) if when == "current" else 0
    available = balance + expected
    needed, without_rest = result["needed"], available - rest  # the balance includes the unspent budget
    result.update(
        balance=balance,
        expected_income=expected,
        no_income_yet=when == "current" and not expected and not data["totals"]["income"],
        keep_for_next=min(rest, max(0, needed - without_rest)),  # part of the leftover next month needs
        saveable=max(0, min(rest, available - needed)),         # part of the leftover that can be saved
        short=max(0, needed - available),                       # still missing with the leftover kept
        short_if_spent=max(0, needed - without_rest),           # missing if the rest of the budget is spent
        spare=max(0, available - needed),                       # everything beyond what next month needs
    )
    return result


# ---- Plans ----

def plans(conn):
    changes = {}
    for r in conn.execute("SELECT * FROM plan_changes ORDER BY start_month"):
        changes.setdefault(r["plan_id"], []).append({"id": r["id"], "start_month": r["start_month"], "amount": r["amount_cents"]})
    return [
        {"id": r["id"], "kind": r["kind"], "name": r["name"], "amount": r["amount_cents"],
         "start_month": r["start_month"], "end_month": r["end_month"], "changes": changes.get(r["id"], [])}
        for r in conn.execute("SELECT * FROM plans ORDER BY kind, start_month, name")
    ]


def amount_at(plan, month):
    """A plan's amount in a month: the latest change from that month or before, else its starting amount."""
    amount = plan["amount"]
    for change in plan["changes"]:
        if change["start_month"] <= month:
            amount = change["amount"]
    return amount


def planned_in(all_plans, kind, month):
    return sum(amount_at(p, month) for p in all_plans
               if p["kind"] == kind and p["start_month"] <= month and (not p["end_month"] or p["end_month"] >= month))


# ---- Projection ----

def buffer_setting(conn):
    return {"mode": setting(conn, "buffer_mode") or "months",
            "months": float(setting(conn, "buffer_months") or 1),
            "amount": int(setting(conn, "buffer_amount") or 0)}


def projection(conn):
    bank, savings = (expected_balance(conn, a, today()) for a in ("bank", "savings"))
    if bank is None or savings is None or None in (starting_point(conn, "bank")[0], starting_point(conn, "savings")[0]):
        return {"visible": False}
    all_plans = plans(conn)
    now = current_month()
    following = next_month(now)
    months = [now]
    for _ in range(HORIZON + 1):
        months.append(next_month(months[-1]))
    budget_of = {m: budget_total(conn, m) for m in months}
    # Next month: its budget plus what's carried into it, minus bills already paid. Carried
    # money is assumed to be spent then; it isn't savings.
    needs = next_month_needs(conn, now)
    still_to_pay = lambda m: needs["needed"] if m == following else budget_of[m]
    buffer = buffer_setting(conn)
    buffer_for = lambda m: buffer["amount"] if buffer["mode"] == "amount" else round(budget_of[m] * buffer["months"])

    current = month_data(conn, now)
    to_come = income_to_come(conn, now, current)
    total = bank + savings - current["leftover"]["rest"] + to_come
    rows = []
    for k, month in enumerate(months[:HORIZON + 1]):
        row = {"month": month, "now": k == 0}
        if k == 0:
            # What this month costs if the rest of its budgets is spent; "planned" is what
            # was spent outside them.
            totals = current["totals"]
            left = sum(max(0, l["available"] - l["spent"]) for g in current["groups"] for l in g["lines"] if l["budget"] is not None)
            row.update(income=totals["income"] + to_come, budget=totals["budget"], planned=totals["outside"],
                       result=totals["income"] + to_come - totals["spent"] - left)
        else:
            row.update(income=planned_in(all_plans, "income", month),
                       budget=needs["budget"] if month == following else budget_of[month],
                       planned=planned_in(all_plans, "expense", month))
            row["result"] = row["income"] - still_to_pay(month) - row["planned"]
            total += row["result"]
        after = next_month(month)
        row["savings"] = total - still_to_pay(after)
        row["buffer"] = buffer_for(after)
        row["above"] = row["savings"] - row["buffer"]  # savings above the buffer this month
        rows.append(row)

    # Free to spend in a month is limited by every month after it: money is only free if
    # no later month needs it to stay above the buffer. A later shortfall means nothing is free.
    lowest = None
    for row in reversed(rows):
        lowest = row["above"] if lowest is None else min(lowest, row["above"])
        row["free"] = max(0, lowest)
        row["later"] = max(0, row["above"]) - row["free"]
    low = min(rows, key=lambda r: r["above"])  # the first of the lowest points
    first_below = next((r["month"] for r in rows if r["above"] < 0), None)
    ready = month_outlook(conn, now, current)  # the same answer as on the overview
    return {"visible": True, "savings_today": savings, "rows": rows, "buffer": buffer,
            "next_month": {"month": following, "short": ready["short"], "short_if_spent": ready["short_if_spent"],
                           "awaiting_income": bool(ready["expected_income"] or ready["no_income_yet"])},
            "low_month": low["month"], "low_above": low["above"], "first_below": first_below}
