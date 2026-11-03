"""Takes the README screenshots of the real app, using made-up demo data in a temporary
folder. Never touches real data. Needs Playwright with WebKit in the build environment:

    .venv-build/bin/pip install playwright && .venv-build/bin/playwright install webkit
    .venv-build/bin/python packaging/make_screenshots.py
"""
import sys
import tempfile
import threading
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from app import db, outlook
from app.demo import seed
from app.web import make_server

OUT = ROOT / "docs" / "screenshots"


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
        page.wait_for_selector("#balance-dialog[open]")
        page.fill("#check-form [name=amount]", "11600")
        page.wait_for_timeout(400)
        page.locator("#balance-dialog").screenshot(path=OUT / "savings.png")
        page.context.close()

        # Looking back on the year.
        page = page_for("light", height=1180)
        page.goto(url + "#history")
        page.wait_for_selector("#history-chart svg")
        page.wait_for_timeout(500)
        shot(page, "history")
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

        # A finished month in review.
        page = page_for("light", height=900)
        page.click('[aria-label="Previous month"]')
        page.wait_for_timeout(500)
        page.locator(".total-card").screenshot(path=OUT / "review.png")
        page.context.close()

        # Reviewing a (made-up) bank export before importing it.
        page = page_for("dark", height=1100)
        page.set_input_files("#bank-file", bank_export())
        page.wait_for_selector("#bank-dialog[open]")
        page.evaluate("document.activeElement.blur()")
        page.wait_for_timeout(400)
        page.locator("#bank-dialog").screenshot(path=OUT / "import.png")
        page.context.close()

        # Settings.
        page = page_for("light", height=880)
        page.click("#settings-btn")
        page.wait_for_timeout(300)
        page.evaluate("document.activeElement.blur()")
        page.locator("#settings").screenshot(path=OUT / "appearance.png")
        page.click("#import-btn")
        page.wait_for_selector("#restore-dialog[open]")
        page.mouse.move(0, 0)
        page.wait_for_timeout(300)
        page.locator("#restore-dialog").screenshot(path=OUT / "restore.png")
        page.context.close()
        browser.close()


def make_daily_backups():
    """A few automatic backups, as if Budget was used on the last days."""
    import shutil
    db.daily_backup()
    today = next(db.BACKUP_DIR.glob("budget-*.db"))
    for days in (1, 2, 4):
        shutil.copy(today, db.BACKUP_DIR / f"budget-{date.today() - timedelta(days=days)}.db")


def bank_export():
    """A made-up ING export: a card payment at a known shop, the rent that's already in the
    demo data, a transfer to savings, and a payment to someone new."""
    with db.connect() as conn:
        rent = conn.execute("SELECT date, amount_cents FROM expenses WHERE payee = 'Oakwood Rentals' ORDER BY date DESC").fetchone()
    day = date.today() - timedelta(days=1)
    ing = lambda d: d.strftime("%Y%m%d")
    euros = lambda c: f"{c // 100},{c % 100:02d}"
    rows = [
        (ing(date.today()), "BCK*FRESH MARKET 0412 NLD", "", "BA", "Af", "23,40", "Betaalautomaat",
         f"Kaartnr: 1234 56** **** 7890 Datum: {day:%d-%m-%Y} Tijd: 17:42 Apple Pay"),
        (ing(date.fromisoformat(rent["date"])), "Oakwood Rentals", "NL00BANK0123456789", "GT", "Af", euros(rent["amount_cents"]),
         "Online bankieren", "Naam: Oakwood Rentals Omschrijving: Rent IBAN: NL00BANK0123456789"),
        (ing(day), "Oranje Spaarrekening", "", "GT", "Af", "150,00", "Online bankieren", "Naar Oranje spaarrekening A12345678"),
        (ing(day), "Studio Lumen", "NL00BANK0987654321", "IW", "Af", "64,00", "iDEAL", "Naam: Studio Lumen Omschrijving: Photo prints IBAN: NL00BANK0987654321"),
    ]
    header = ["Datum", "Naam / Omschrijving", "Rekening", "Tegenrekening", "Code", "Af Bij", "Bedrag (EUR)", "Mutatiesoort", "Mededelingen"]
    lines = [header] + [[r[0], r[1], "NL00INGB0000000000", *r[2:]] for r in rows]
    return {"name": "export.csv", "mimeType": "text/csv",
            "buffer": "\n".join(",".join(f'"{v}"' for v in line) for line in lines).encode()}


def main():
    with tempfile.TemporaryDirectory() as folder:
        db.use_data_dir(Path(folder))
        db.migrate()
        seed()
        make_daily_backups()
        outlook.READY_DAYS = 31  # show "ready for next month?" whatever today's date is
        server = make_server(0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        capture(f"http://127.0.0.1:{server.server_address[1]}/")
        server.shutdown()
    print(f"Saved screenshots to {OUT}")


if __name__ == "__main__":
    main()
