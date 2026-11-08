"""A made-up household, for trying out the app and for the README screenshots."""
import random
from datetime import date

from . import api, db

TODAY = date.today()
YEAR = TODAY.year
MONTHS = [f"{YEAR}-{m:02d}" for m in range(1, TODAY.month + 1)]
THIS_MONTH, FIRST = MONTHS[-1], MONTHS[0]
NEXT_MONTH = f"{YEAR + TODAY.month // 12}-{TODAY.month % 12 + 1:02d}"

# Budgets in euros: {category: {item: amount}}, or {category: amount} without items.
BUDGETS = {
    "Home": {"Rent": 950, "Energy": 120, "Internet": 45},
    "Groceries": {"Food": 320, "Household": 60},
    "Subscriptions": {"Streaming": 18, "Phone": 25, "Gym": 35},
    "Transport": 80,
    "Fun money": 250,
}


def seed():
    with db.session() as conn:
        lines = {}

        def add_budget(category, spec):
            api.create_category(conn, None, {"name": category, "budget": 0 if isinstance(spec, dict) else spec * 100, "month": FIRST}, None)
            cat_id = conn.execute("SELECT id FROM categories WHERE name = ?", (category,)).fetchone()["id"]
            if not isinstance(spec, dict):
                lines[category] = {"category_id": cat_id}
                return
            for item, amount in spec.items():
                api.create_item(conn, None, {"category_id": cat_id, "name": item, "budget": amount * 100, "month": FIRST}, None)
                lines[item] = {"item_id": conn.execute("SELECT id FROM items WHERE name = ?", (item,)).fetchone()["id"]}

        for category, spec in BUDGETS.items():
            add_budget(category, spec)
        api.change_budget(conn, None, {**lines["Fun money"], "month": FIRST, "amount": 25000, "rollover": True}, None)

        def add(day, payee, amount, line=None, note="", kind="expense", splits=None):
            if day > TODAY.isoformat():
                return
            if splits is None:
                splits = [{**lines[line], "amount": amount}] if line else []
            api.save_transaction(conn, None, {"kind": kind, "date": day, "amount": amount, "payee": payee,
                                              "description": note, "splits": splits}, None)

        random.seed(7)
        for month in MONTHS:
            add(f"{month}-01", "Oakwood Rentals", 95000, "Rent")
            add(f"{month}-02", "Pulse Fitness", 3500, "Gym")
            add(f"{month}-03", "Bright Energy", random.randint(9500, 11800), "Energy")
            add(f"{month}-05", "FiberNet", 4500, "Internet")
            add(f"{month}-06", "Streamly", 1800, "Streaming")
            add(f"{month}-08", "Mobile Co", 2500, "Phone")
            add(f"{month}-25", "Northwind Ltd", 285000, note="Salary", kind="income")
            add(f"{month}-26", "", 85000, note="Monthly savings", kind="save")
            for day in (4, 9, 13, 18, 22, 27):
                add(f"{month}-{day:02d}", random.choice(["Fresh Market", "Corner Grocer", "Daily Foods"]), random.randint(3200, 6200), "Food")
            for day in (11, 24):
                add(f"{month}-{day:02d}", "Home & Co", random.randint(1200, 2600), "Household")
            for day in (7, 15, 23):
                add(f"{month}-{day:02d}", "City Transit", random.randint(1500, 2600), "Transport")
            for day, payee, note in ((10, "Bistro Luna", "Dinner with friends"), (16, "Paper & Ink", "Books"), (20, "Cinema Lux", "Movie night")):
                add(f"{month}-{day:02d}", payee, random.randint(6500, 9800), "Fun money", note)

        # This month: a split purchase, spending outside the budgets, and income for a budget.
        add(f"{THIS_MONTH}-12", "Green Pharmacy", 4800, note="Hand soap and vitamins",
            splits=[{**lines["Household"], "amount": 1800}, {**lines["Fun money"], "amount": 3000}])
        add(f"{THIS_MONTH}-14", "Dr. Rivers", 14000, note="Dentist")
        add(f"{THIS_MONTH}-17", "Secondhand Market", 3500, note="Sold a lamp", kind="income",
            splits=[{**lines["Fun money"], "amount": 3500}])

        # Balances, one check against the bank, and plans for the outlook.
        start = f"{YEAR}-01-01"
        api.set_balance_start(conn, None, {"account": "bank", "amount": 180000, "date": start}, None)
        api.set_balance_start(conn, None, {"account": "savings", "amount": 310000, "date": start}, None)
        bank = api.get_balance(conn, None, None, {"account": ["bank"]})["expected"]
        api.add_balance_check(conn, None, {"account": "bank", "date": TODAY.isoformat(), "amount": bank}, None)
        api.save_plan(conn, None, {"kind": "income", "name": "Salary", "amount": 285000, "start_month": NEXT_MONTH}, None)
        plan = conn.execute("SELECT id FROM plans").fetchone()["id"]
        api.add_plan_change(conn, None, {"plan_id": plan, "start_month": f"{YEAR + 1}-03", "amount": 300000}, None)
        for name, month, amount in (("Car service", NEXT_MONTH, 48000), ("Summer holiday", f"{YEAR + 1}-06", 180000),
                                    ("New laptop", f"{YEAR + 1}-02", 110000)):
            api.save_plan(conn, None, {"kind": "expense", "name": name, "amount": amount, "start_month": month, "end_month": month}, None)
