"""Deleting all data: final, with nothing left behind."""
from app import api, backup, db
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

    def test_cannot_be_undone_and_leaves_no_copies(self):
        db.daily_backup()
        backup.restore(backup.export_file()[1])  # an import leaves a safety copy
        self.assertTrue(backup.status()["can_undo"])
        api.clear_data(self.conn, None, {"confirm": True}, None)
        self.assertFalse(backup.status()["can_undo"])
        self.assertEqual(list(db.BACKUP_DIR.glob("*.db")), [])
