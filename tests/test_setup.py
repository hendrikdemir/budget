"""The getting-started guide: which steps are done."""
from app import api
from app.money import ApiError

from .base import AppTest


class GettingStarted(AppTest):
    def steps(self):
        return api.get_setup(self.conn, None, None, None)["steps"]

    def test_nothing_is_done_at_first(self):
        self.assertEqual(self.steps(), {"bank": False, "savings": False, "budgets": False, "transaction": False, "income": False})

    def test_each_step_is_done_by_what_it_asks_for(self):
        self.start_balance("bank", 100000, "2026-11-01")
        self.category("Home")  # a category without a budget isn't a budget yet
        self.assertEqual(self.steps(), {"bank": True, "savings": False, "budgets": False, "transaction": False, "income": False})
        self.start_balance("savings", 0, "2026-11-01")
        self.category("Fun money", 10000)
        self.add(1250, "2026-11-02")
        self.plan("expense", 50000, "2026-12", "2026-12")  # a planned cost isn't expected income
        self.assertEqual(self.steps(), {"bank": True, "savings": True, "budgets": True, "transaction": True, "income": False})
        self.plan("income", 250000, "2026-12")
        self.assertTrue(all(self.steps().values()))

    def test_hiding_the_guide(self):
        self.assertFalse(api.get_setup(self.conn, None, None, None)["hidden"])
        api.save_settings(self.conn, None, {"guide": "hidden"}, None)
        self.assertTrue(api.get_setup(self.conn, None, None, None)["hidden"])
        with self.assertRaises(ApiError):
            api.save_settings(self.conn, None, {"guide": "maybe"}, None)
