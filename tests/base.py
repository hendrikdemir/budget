"""Shared setup for the tests: an empty database in a temporary folder, a fixed "today",
and short helpers to add budgets and transactions through the same API the page uses.
All data is made up."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import accounts, api, budgets, db, outlook


class AppTest(unittest.TestCase):
    TODAY = "2026-11-15"

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        db.use_data_dir(Path(self.folder.name))
        db.migrate()
        self.conn = db.connect()
        self.patches = []
        self.on(self.TODAY)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.conn.close()
        self.folder.cleanup()

    def on(self, day):
        """Pretend today is `day` ("YYYY-MM-DD")."""
        for p in self.patches:
            p.stop()
        self.patches = [mock.patch.object(module, name, value) for module, name, value in (
            (budgets, "current_month", lambda: day[:7]),
            (outlook, "current_month", lambda: day[:7]),
            (outlook, "today", lambda: day),
            (accounts, "today", lambda: day),
            (api, "current_month", lambda: day[:7]),
        )]
        for p in self.patches:
            p.start()

    # ---- Making data ----

    def category(self, name, budget=None, month="2026-01"):
        """A category; with `budget`, one without items. Returns its id."""
        api.create_category(self.conn, None, {"name": name, "month": month, "budget": budget or 0}, None)
        return self.conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()["id"]

    def item(self, category_id, name, budget, month="2026-01", carry=None):
        """An item with a budget from `month`. Returns its line key, e.g. "i3"."""
        api.create_item(self.conn, None, {"category_id": category_id, "name": name, "month": month, "budget": budget}, None)
        item_id = self.conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
        if carry is not None:
            self.change(f"i{item_id}", month, budget, carry)
        return f"i{item_id}"

    def change(self, line, month, amount, carry=None):
        target = {"item_id" if line[0] == "i" else "category_id": int(line[1:])}
        api.change_budget(self.conn, None, {**target, "month": month, "amount": amount, "rollover": carry}, None)

    def add(self, amount, day, line=None, kind="expense", payee="Shop", paid_date=None):
        splits = []
        if line:
            splits = [{"item_id" if line[0] == "i" else "category_id": int(line[1:]), "amount": amount}]
        api.save_transaction(self.conn, None, {"amount": amount, "date": day, "kind": kind, "payee": payee,
                                               "splits": splits, "paid_date": paid_date}, None)

    def start_balance(self, account, amount, day):
        api.set_balance_start(self.conn, None, {"account": account, "amount": amount, "date": day}, None)

    def plan(self, kind, amount, start, end=None, name="Plan"):
        api.save_plan(self.conn, None, {"kind": kind, "name": name, "amount": amount, "start_month": start, "end_month": end}, None)

    # ---- Reading results ----

    def month(self, month):
        return budgets.month_data(self.conn, month)

    def line(self, month, key):
        data = self.month(month)
        return next(l for g in data["groups"] for l in g["lines"] if l["key"] == key)
