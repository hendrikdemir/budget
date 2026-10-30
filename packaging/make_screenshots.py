"""Takes the README screenshots of the real app, using made-up demo data in a temporary
folder. Never touches real data. Needs Playwright with WebKit in the build environment:

    .venv-build/bin/pip install playwright && .venv-build/bin/playwright install webkit
    .venv-build/bin/python packaging/make_screenshots.py
"""
import random
import sys
import tempfile
import threading
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from app import api, db
from app.web import make_server

OUT = ROOT / "docs" / "screenshots"
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
    with db.connect() as conn:
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


def capture(url):
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.webkit.launch()

        def page_for(scheme, width=1000, height=1000):
            context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2,
                                          color_scheme=scheme, locale="en-GB")
            page = context.new_page()
            page.goto(url)
            page.wait_for_selector(".account-row .balance-amount:not(:empty)")
            page.wait_for_timeout(600)
            return page

        def shot(page, name, **kwargs):
            page.screenshot(path=OUT / f"{name}.png", **kwargs)

        # The overview, in both themes.
        for scheme in ("dark", "light"):
            page = page_for(scheme, height=1040)
            shot(page, f"overview-{scheme}")
            page.context.close()

        page = page_for("dark", height=1200)
        page.click("#expand-all")
        page.mouse.move(0, 0)
        page.wait_for_timeout(300)
        page.locator("#budgets").locator("xpath=..").screenshot(path=OUT / "budgets.png")

        # Search in the transactions.
        page.fill("#search", "fresh")
        page.wait_for_timeout(300)
        page.evaluate("document.querySelector('#expenses').style.maxHeight = '430px'; document.querySelector('#expenses').style.overflow = 'hidden'")
        page.locator("#expenses").locator("xpath=..").screenshot(path=OUT / "transactions.png")
        page.fill("#search", "")

        # A split expense with its effect on both budgets.
        page.click("#add-btn")
        page.wait_for_selector("#expense-dialog[open]")
        page.fill("#add-form [name=amount]", "45")
        page.fill("#add-form [name=payee]", "Paper & Ink")
        page.fill("#add-form [name=description]", "Birthday present")
        page.click("#add-split")
        rows = page.locator(".split")
        rows.nth(0).locator(".split-line").click()
        page.keyboard.type("Fun")
        page.keyboard.press("ArrowDown"); page.keyboard.press("Enter")
        rows.nth(0).locator(".split-amount").fill("35")
        rows.nth(1).locator(".split-line").click()
        page.keyboard.type("Household")
        page.keyboard.press("ArrowDown"); page.keyboard.press("Enter")
        page.locator("#expense-title").click()
        page.wait_for_timeout(400)
        page.locator("#expense-dialog").screenshot(path=OUT / "transaction.png")
        page.keyboard.press("Escape")
        page.context.close()

        # The savings development.
        page = page_for("dark", height=1000)
        page.click('.account-row[data-account="savings"]')
        page.wait_for_selector("#hist-plot svg")
        page.wait_for_timeout(400)
        page.locator("#balance-dialog").screenshot(path=OUT / "savings.png")
        page.context.close()

        # The outlook.
        page = page_for("dark", height=1040)
        page.goto(url + "#outlook")
        page.wait_for_selector("#outlook-chart svg")
        page.wait_for_timeout(500)
        shot(page, "outlook")
        page.click("#buffer-edit")
        page.wait_for_timeout(300)
        page.locator("#buffer-dialog").screenshot(path=OUT / "buffer.png")
        page.context.close()

        # Appearance.
        page = page_for("light", height=700)
        page.click("#settings-btn")
        page.click('.swatch[data-color="#10b981"]')
        page.wait_for_timeout(300)
        page.locator("#settings").screenshot(path=OUT / "appearance.png")
        page.context.close()
        browser.close()


def main():
    with tempfile.TemporaryDirectory() as folder:
        db.use_data_dir(Path(folder))
        db.migrate()
        seed()
        server = make_server(0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        capture(f"http://127.0.0.1:{server.server_address[1]}/")
        server.shutdown()
    print(f"Saved screenshots to {OUT}")


if __name__ == "__main__":
    main()
