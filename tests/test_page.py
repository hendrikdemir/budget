"""The page itself, in WebKit (the engine of the Mac app), with real clicks: every page and
dialog in English and Dutch, in Simple and Extended mode, at desktop and phone width, without
errors, untranslated keys or anything wider than the window; names shown as text whatever they
contain; and a new user's first steps.

Needs Playwright with WebKit (in .venv-build, see packaging/make_screenshots.py); without it
these tests are skipped. Run them with:  .venv-build/bin/python -m unittest tests.test_page
"""
import re
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # the app itself doesn't need Playwright
    sync_playwright = None

from app import api, db, demo
from app.web import make_server

KEY = re.compile(r"\b(?:app|common|overview|budgets|transaction|accounts|outlook|history|settings|backup|import|updates|guide|help|errors)\.[a-z]\w+")
SIZES = {"desktop": (1100, 900), "phone": (390, 844)}
# A name that would run a script if it were ever put into the page as HTML.
HOSTILE = '<img src=x onerror="window.injected=1">'


@unittest.skipIf(sync_playwright is None, "Playwright isn't installed (see the top of this file)")
class PageTest(unittest.TestCase):
    seed = None  # what to put in the data before the browser opens

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        db.use_data_dir(Path(cls.folder.name))
        db.migrate()
        if cls.seed:
            cls.seed()
        cls.server = make_server(0)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.webkit.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.folder.cleanup()

    def settings(self, **values):
        with db.session() as conn:
            api.save_settings(conn, None, values, None)

    def open(self, hash_="", size="desktop", scheme="light"):
        """A fresh page; fails the test on any error in it."""
        width, height = SIZES[size]
        page = self.browser.new_page(viewport={"width": width, "height": height}, color_scheme=scheme, locale="en-GB")
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        page.goto(self.url + hash_)
        page.wait_for_selector("#month-btn:not(:empty)", state="attached")  # (the page's security policy allows no wait_for_function)
        page.wait_for_timeout(300)
        self.addCleanup(page.close)
        return page

    def check(self, page, where):
        """No errors, no untranslated keys and nothing wider than the window."""
        page.wait_for_timeout(250)
        self.assertEqual(self.errors, [], where)
        text = page.evaluate("document.body.innerText")
        self.assertEqual(KEY.findall(text), [], f"untranslated in {where}")
        overflow = page.evaluate("""() => [...document.querySelectorAll('body *')].filter((el) => {
            const box = el.getBoundingClientRect();
            return box.width && box.right > innerWidth + 1 && !el.closest('.table-wrap, .hist-plot, [hidden]');
          }).map((el) => el.tagName + '.' + el.className).slice(0, 5)""")
        self.assertEqual(overflow, [], f"wider than the window in {where}")


class EveryScreen(PageTest):
    """The made-up household, everywhere."""
    seed = staticmethod(demo.seed)

    def dialogs(self, page, where, extended):
        for opener, dialog in [("#settings-btn", "#settings"), ("#manage-btn", "#manager"), ("#add-btn", "#expense-dialog"),
                               ("#income-btn", "#expense-dialog"), ('.account-row[data-account="bank"]', "#balance-dialog")]:
            page.locator(opener).first.click()
            page.wait_for_selector(f"{dialog}[open]")
            self.check(page, f"{where}, {dialog}")
            page.keyboard.press("Escape")
            page.wait_for_selector(f"{dialog}:not([open])", state="attached")
        if extended:
            page.goto(self.url + "#outlook")
            page.wait_for_selector("#outlook-chart svg")
            self.check(page, f"{where}, Outlook")
            page.click('[data-add-plan="income"]')
            page.wait_for_selector("#plan-dialog[open]")
            self.check(page, f"{where}, plan")
            page.keyboard.press("Escape")
            page.click("#buffer-edit")
            page.wait_for_selector("#buffer-dialog[open]")
            self.check(page, f"{where}, buffer")
            page.keyboard.press("Escape")

    def test_every_page_and_dialog(self):
        for language in ("en", "nl"):
            for mode in ("simple", "full"):
                self.settings(language=language, mode=mode)
                for size in SIZES:
                    where = f"{language}, {mode}, {size}"
                    with self.subTest(where):
                        page = self.open(size=size, scheme="dark" if size == "phone" else "light")
                        self.check(page, f"{where}, overview")
                        self.assertEqual(page.locator('.tabs a[data-view="outlook"]').is_visible(), mode == "full")
                        page.goto(self.url + "#history")
                        page.wait_for_selector("#history-chart svg")
                        self.check(page, f"{where}, History")
                        page.goto(self.url)
                        page.wait_for_timeout(300)
                        self.dialogs(page, where, mode == "full")
        self.settings(language="system", mode="full")

    def test_chart_tooltip_beside_the_month(self):
        page = self.open("#history")
        page.wait_for_selector("#history-chart svg")
        hit = page.locator("#history-chart .hit").first
        hit.hover()
        tip, line = page.locator("#history-chart .hist-tip").bounding_box(), page.locator("#history-chart .crosshair").bounding_box()
        self.assertTrue(tip["x"] > line["x"] or tip["x"] + tip["width"] < line["x"], "the tooltip covers the month it's about")


class NamesStayText(PageTest):
    """Whatever a payee, note, budget or plan is called, it shows as text and never runs."""

    @staticmethod
    def seed():
        month = date.today().isoformat()[:7]
        with db.session() as conn:
            api.create_category(conn, None, {"name": HOSTILE, "budget": 10000, "month": month}, None)
            category = conn.execute("SELECT id FROM categories").fetchone()["id"]
            api.save_transaction(conn, None, {"kind": "expense", "date": f"{month}-01", "amount": 1250, "payee": HOSTILE,
                                              "description": HOSTILE, "splits": [{"category_id": category, "amount": 1250}]}, None)
            api.save_plan(conn, None, {"kind": "income", "name": HOSTILE, "amount": 100000, "start_month": month}, None)
            api.save_settings(conn, None, {"mode": "full"}, None)

    def test_hostile_names_are_shown_as_text(self):
        page = self.open()
        page.click("#manage-btn")
        page.wait_for_selector("#manager[open]")
        page.keyboard.press("Escape")
        page.goto(self.url + "#outlook")
        page.wait_for_selector("#plans-income li")
        page.goto(self.url)
        page.wait_for_selector("#expenses .expense")
        self.assertIsNone(page.evaluate("window.injected"))
        self.assertEqual(page.locator("img[src=x]").count(), 0)
        self.assertIn(HOSTILE, page.locator("#expenses").inner_text())
        self.assertIn(HOSTILE, page.locator("#budgets").inner_text())
        self.assertEqual(self.errors, [])


class FirstSteps(PageTest):
    """A new user: two steps, budgets from the suggestions, then a first expense."""

    def test_start_with_budgets_and_an_expense(self):
        self.settings(language="en")
        page = self.open()
        self.assertEqual(page.locator("#guide .guide-step").count(), 2)
        self.assertFalse(page.locator(".accounts").is_visible())  # the bank balance is offered later
        page.click("#guide [data-run]")
        page.wait_for_selector("#starter:not([hidden]) .starter-row")
        income = page.locator("#fit-income-form [name=amount]")
        income.fill("2500")
        amounts = page.locator("#starter .starter-row .amount")
        amounts.nth(0).click()  # leaving the income field saves it
        page.wait_for_selector("#fit-income-change")
        page.locator("#starter .starter-row .amount").nth(0).fill("950")
        page.locator("#starter .starter-row .amount").nth(4).fill("350")
        page.locator("#starter-add").click()
        page.wait_for_selector("#manager:not([open])", state="attached")
        self.assertIn("Groceries", page.locator("#budgets").inner_text())

        page.click("#add-btn")
        page.wait_for_selector("#expense-dialog[open]")
        page.fill("#add-form [name=amount]", "23.40")
        page.fill("#add-form [name=payee]", "Fresh Market")
        page.locator(".split .split-line").click()
        page.keyboard.type("Groc")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        page.click("#expense-submit")
        page.wait_for_selector("#expense-dialog:not([open])", state="attached")
        self.assertIn("Fresh Market", page.locator("#expenses").inner_text())
        self.assertFalse(page.locator("#guide").is_visible())  # both steps done
        self.check(page, "after the first steps")
