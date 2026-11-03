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

    def test_leaves_no_copies(self):
        db.daily_backup()
        api.clear_data(self.conn, None, {"confirm": True}, None)
        self.assertEqual(list(db.BACKUP_DIR.glob("*.db")), [])


class Restore(AppTest):
    def test_replaces_everything_and_keeps_no_copy(self):
        self.add(1250, "2026-11-01", payee="Corner Grocer")
        self.conn.commit()
        saved = backup.export_file()[1]
        self.add(900, "2026-11-02", payee="Fresh Market")
        self.conn.commit()
        backup.restore(saved)
        payees = [r[0] for r in self.conn.execute("SELECT payee FROM expenses")]
        self.assertEqual(payees, ["Corner Grocer"])
        self.assertEqual(list(db.BACKUP_DIR.glob("before-*.db")) if db.BACKUP_DIR.exists() else [], [])


class AutomaticBackups(AppTest):
    def test_listed_and_restorable(self):
        self.add(1250, "2026-11-01", payee="Corner Grocer")
        self.conn.commit()
        db.daily_backup()
        self.add(900, "2026-11-02", payee="Fresh Market")
        self.conn.commit()
        (copy,) = backup.auto_backups()
        self.assertEqual(copy["transactions"], 1)
        self.assertEqual(backup.check_auto(copy["name"])["current"]["transactions"], 2)
        backup.restore_auto(copy["name"])
        self.assertEqual([r[0] for r in self.conn.execute("SELECT payee FROM expenses")], ["Corner Grocer"])

    def test_only_its_own_files(self):
        for name in ("../budget.db", "budget-2026-11-01.db", "before-import-x.db"):
            with self.assertRaises(ApiError):
                backup.restore_auto(name)
