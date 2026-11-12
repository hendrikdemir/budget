"""Takes the README screenshots of the real app, using made-up demo data in a temporary
folder. Never touches real data. Needs Playwright with WebKit in the build environment:

    .venv-build/bin/pip install playwright && .venv-build/bin/playwright install webkit
    .venv-build/bin/python packaging/make_screenshots.py
"""
import os
import sys
import tempfile
import threading
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from app import VERSION, api, db, outlook, updates
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
        page.check("#all-months")  # early in the month, the shop is mostly in earlier months
        page.fill("#search", "fresh")
        page.wait_for_timeout(500)
        page.evaluate("document.querySelector('#expenses').style.maxHeight = '430px'; document.querySelector('#expenses').style.overflow = 'hidden'")
        page.locator("#expenses").locator("xpath=..").screenshot(path=OUT / "transactions.png")
        page.fill("#search", "")
        page.uncheck("#all-months")

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
        page.mouse.move(0, 0)
        page.locator("#history-budgets-card").screenshot(path=OUT / "budget-history.png")
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
        # The outlook in the light theme, for the landing page.
        page = page_for("light", height=1040)
        page.goto(url + "#outlook")
        page.wait_for_selector("#outlook-chart svg")
        page.wait_for_timeout(500)
        shot(page, "outlook-light")
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

        # A new version is available.
        fake_release(NEWER)
        page = page_for("light", height=880)
        page.click("#update-how")
        page.wait_for_selector("#update-dialog[open]")
        page.evaluate("document.activeElement.blur()")
        page.mouse.move(0, 0)
        page.wait_for_timeout(300)
        page.locator("#update-dialog").screenshot(path=OUT / "update.png")
        page.context.close()

        # Where to find Open Anyway: a drawing, so it's in English whatever the Mac's language.
        page = browser.new_page(viewport={"width": 760, "height": 480}, device_scale_factor=2)
        page.set_content(OPEN_ANYWAY)
        page.wait_for_timeout(200)
        page.locator(".window").screenshot(path=OUT / "open-anyway.png")
        page.close()
        browser.close()


# A simplified System Settings window, Privacy & Security scrolled down to Security.
OPEN_ANYWAY = """<!doctype html><meta charset="utf-8"><style>
  * { box-sizing: border-box; margin: 0; }
  body { padding: 24px; background: #f0f6f0; font: 13px/1.35 -apple-system, BlinkMacSystemFont, sans-serif;
         color: #1d1d1f; -webkit-font-smoothing: antialiased; }
  .window { display: flex; width: 712px; height: 432px; border-radius: 12px; overflow: hidden; background: #fff;
            border: 1px solid #d5d5d8; box-shadow: 0 18px 40px rgba(54, 73, 88, .22); }
  .side { width: 214px; background: #ecebef; padding: 14px 10px; border-right: 1px solid #dcdce0; }
  .dots { display: flex; gap: 8px; margin: 0 0 16px 4px; }
  .dots i { width: 12px; height: 12px; border-radius: 50%; background: #d1d1d6; }
  .search { height: 26px; border-radius: 7px; background: #dedde2; color: #8e8e93; padding: 5px 9px; margin-bottom: 12px; }
  .item { display: flex; align-items: center; gap: 8px; padding: 5px 7px; border-radius: 7px; margin-bottom: 1px; color: #3a3a3c; }
  .item b { width: 20px; height: 20px; border-radius: 5px; flex: none; }
  .item.on { background: #3b6064; color: #fff; }
  .main { flex: 1; padding: 16px 26px; overflow: hidden; }
  h1 { font-size: 15px; font-weight: 600; margin-bottom: 14px; }
  .faded { color: #a1a1a6; }
  .group { border: 1px solid #e3e3e8; border-radius: 9px; background: #fafafc; margin-bottom: 14px; }
  .row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 13px; }
  .row + .row { border-top: 1px solid #ebebef; }
  h2 { font-size: 13px; font-weight: 600; margin: 4px 0 8px; }
  .pop { border: 1px solid #d1d1d6; border-radius: 6px; padding: 3px 9px; background: #fff; white-space: nowrap; }
  .btn { position: relative; border: 1px solid #c7c7cc; border-radius: 6px; padding: 4px 12px; background: #fff;
         font-weight: 500; white-space: nowrap; }
  .btn::after { content: ""; position: absolute; inset: -7px; border: 3px solid #c8372d; border-radius: 11px; }
  .hint { margin-top: 10px; font-size: 12px; color: #55828b; font-weight: 500; text-align: right; }
</style>
<div class="window">
  <div class="side">
    <div class="dots"><i></i><i></i><i></i></div>
    <div class="search">Search</div>
    <div class="item"><b style="background:#8e8e93"></b>General</div>
    <div class="item"><b style="background:#5e9fd9"></b>Appearance</div>
    <div class="item"><b style="background:#e3a33b"></b>Notifications</div>
    <div class="item"><b style="background:#6f6fd6"></b>Focus</div>
    <div class="item"><b style="background:#d7584d"></b>Screen Time</div>
    <div class="item on"><b style="background:#5b8fd6"></b>Privacy &amp; Security</div>
    <div class="item"><b style="background:#9b9ba1"></b>Desktop &amp; Dock</div>
    <div class="item"><b style="background:#4f9ae6"></b>Displays</div>
    <div class="item"><b style="background:#62b06b"></b>Battery</div>
  </div>
  <div class="main">
    <h1>Privacy &amp; Security</h1>
    <div class="group faded"><div class="row">Location Services<span>›</span></div><div class="row">Full Disk Access<span>›</span></div></div>
    <p class="faded" style="margin:-4px 0 12px">⋮ scroll down</p>
    <h2>Security</h2>
    <div class="group">
      <div class="row">Allow applications from<span class="pop">App Store &amp; Known Developers ⌄</span></div>
      <div class="row">“Budget” was blocked to protect your Mac.<span class="btn">Open Anyway</span></div>
    </div>
    <p class="hint">Click Open Anyway, then confirm with your password or Touch ID.</p>
  </div>
</div>"""


RELEASE_FILE = None
NEWER = {"tag_name": "v9.9.0", "body": "- See how this month compares with the same month last year\n- Fixes a rounding issue in the outlook",
         "assets": [{"name": "Budget.dmg", "browser_download_url": "https://github.com/hendrikdemir/budget/releases"}]}


def capture_guide(url):
    """The getting-started guide, as a new user sees it after the first step."""
    with sync_playwright() as p:
        browser = p.webkit.launch()
        page = browser.new_context(viewport={"width": 1000, "height": 800}, device_scale_factor=2,
                                   color_scheme="light", locale="en-GB").new_page()
        page.goto(url)
        page.wait_for_selector("#guide:not([hidden]) .guide-step")
        page.wait_for_timeout(600)
        page.locator("#guide").screenshot(path=OUT / "guide.png")
        browser.close()


def fake_release(release):
    """Makes the update check see `release` instead of asking GitHub."""
    import json
    RELEASE_FILE.write_text(json.dumps(release))
    updates._cache.update(until=0, release=None)


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
    with db.session() as conn:
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
        global RELEASE_FILE
        RELEASE_FILE = Path(folder) / "release.json"
        os.environ["BUDGET_RELEASES_URL"] = str(RELEASE_FILE)
        fake_release({"tag_name": f"v{VERSION}"})  # Settings: "You have the latest version"
        outlook.READY_DAYS = 31  # show "ready for next month?" whatever today's date is
        server = make_server(0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        capture(f"http://127.0.0.1:{server.server_address[1]}/")
        server.shutdown()
    # A new user's first steps: nothing but the balances yet.
    with tempfile.TemporaryDirectory() as folder:
        db.use_data_dir(Path(folder))
        db.migrate()
        with db.session() as conn:
            for account, amount in (("bank", 250000), ("savings", 1160000)):
                api.set_balance_start(conn, None, {"account": account, "amount": amount, "date": date.today().isoformat()}, None)
        server = make_server(0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        capture_guide(f"http://127.0.0.1:{server.server_address[1]}/")
        server.shutdown()
    print(f"Saved screenshots to {OUT}")


if __name__ == "__main__":
    main()
