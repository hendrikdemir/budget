"""Deleting all data, and undoing it."""
from app import api, backup
from app.money import ApiError

from .base import AppTest


class ClearData(AppTest):
    def setUp(self):
        super().setUp()
        self.item(self.category("Groceries"), "Food", 30000)
        self.add(1250, "2026-11-01", payee="Corner Grocer")
        self.start_balance("bank", 100000, "2026-11-01")
        self.plan("income", 250000, "2026-11")
        api.save_settings(self.conn, None, {"theme": "dark", "currency": "USD"}, None)
        self.conn.commit()

    def count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_needs_a_clear_yes(self):
        with self.assertRaises(ApiError):
            api.clear_data(self.conn, None, {}, None)
        self.assertEqual(self.count("expenses"), 1)

    def test_deletes_everything_but_how_it_looks(self):
        api.clear_data(self.conn, None, {"confirm": True}, None)
        for table in ("expenses", "splits", "categories", "items", "budgets", "plans"):
            self.assertEqual(self.count(table), 0, table)
        settings = dict(self.conn.execute("SELECT key, value FROM settings").fetchall())
        self.assertEqual(settings, {"theme": "dark", "currency": "USD"})

    def test_can_be_undone(self):
        api.clear_data(self.conn, None, {"confirm": True}, None)
        self.assertEqual(backup.status(), {"can_undo": True, "last": "delete"})
        backup.undo()
        self.assertEqual((self.count("expenses"), self.count("categories"), self.count("plans")), (1, 1, 1))
        self.assertFalse(backup.status()["can_undo"])
