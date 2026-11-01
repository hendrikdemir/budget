"""Takes the README screenshots of the real app, using made-up demo data in a temporary
folder. Never touches real data. Needs Playwright with WebKit in the build environment:

    .venv-build/bin/pip install playwright && .venv-build/bin/playwright install webkit
    .venv-build/bin/python packaging/make_screenshots.py
"""
import sys
import tempfile
import threading
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

        # Settings.
        page = page_for("light", height=880)
        page.click("#settings-btn")
        page.wait_for_timeout(300)
        page.evaluate("document.activeElement.blur()")
        page.locator("#settings").screenshot(path=OUT / "appearance.png")
        page.context.close()
        browser.close()


def main():
    with tempfile.TemporaryDirectory() as folder:
        db.use_data_dir(Path(folder))
        db.migrate()
        seed()
        outlook.READY_DAYS = 31  # show "ready for next month?" whatever today's date is
        server = make_server(0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        capture(f"http://127.0.0.1:{server.server_address[1]}/")
        server.shutdown()
    print(f"Saved screenshots to {OUT}")


if __name__ == "__main__":
    main()
