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


class Modes(AppTest):
    def settings(self):
        return api.get_settings(self.conn, None, None, None)

    def test_new_data_starts_with_the_basics(self):
        self.assertEqual(self.settings()["mode"], "simple")
        api.save_settings(self.conn, None, {"mode": "full", "language": "nl"}, None)
        self.assertEqual((self.settings()["mode"], self.settings()["language"]), ("full", "nl"))
        for wrong in ({"mode": "maybe"}, {"language": "xx"}, {"offers_dismissed": "outlook,other"}):
            with self.assertRaises(ApiError):
                api.save_settings(self.conn, None, wrong, None)

    def test_data_from_before_keeps_every_feature(self):
        from app import db
        self.category("Fun money", 10000)
        self.conn.commit()
        self.conn.execute("PRAGMA user_version = 2")
        self.conn.execute("DELETE FROM settings WHERE key = 'migrations'")  # as Budget 0.10 left it
        self.conn.commit()
        db.migrate()
        self.assertEqual(self.settings()["mode"], "full")


class Offers(AppTest):
    def offers(self):
        return [o["id"] for o in api.get_setup(self.conn, None, None, None)["offers"]]

    def test_the_outlook_once_a_month_is_kept(self):
        self.start_balance("bank", 100000, "2026-11-01")
        self.add(1000, "2026-11-02")
        self.assertEqual(self.offers(), [])
        self.on("2026-12-03")
        self.assertEqual(self.offers(), ["outlook"])
        api.save_settings(self.conn, None, {"offers_dismissed": "outlook"}, None)
        self.assertEqual(self.offers(), [])

    def test_carry_over_for_a_budget_with_money_left_twice(self):
        food = self.category("Food", 30000)
        fun = self.category("Fun money", 10000)
        self.add(25000, "2026-10-05", f"c{food}")
        self.add(10000, "2026-10-06", f"c{fun}")  # all used: nothing left
        self.add(28000, "2026-11-05", f"c{food}")
        self.on("2026-12-03")
        offer = next(o for o in api.get_setup(self.conn, None, None, None)["offers"] if o["id"] == "carry")
        self.assertEqual((offer["name"], offer["months"]), ("Food", ["2026-10", "2026-11"]))
        api.save_settings(self.conn, None, {"mode": "full"}, None)  # every feature is on already
        self.assertNotIn("carry", self.offers())

    def test_the_bank_balance_after_two_weeks_or_income(self):
        self.add(1000, "2026-11-02")
        self.add(1000, "2026-11-10")
        self.assertNotIn("bank", self.offers())
        self.add(1000, "2026-11-16")  # two weeks of spending
        self.assertIn("bank", self.offers())
        self.start_balance("bank", 100000, "2026-11-01")
        self.assertNotIn("bank", self.offers())

    def test_the_bank_balance_once_income_is_added(self):
        self.add(250000, "2026-11-01", kind="income", payee="Employer")
        self.assertEqual(self.offers()[0], "bank")
        api.save_settings(self.conn, None, {"mode": "full"}, None)  # Extended mode asks for it while getting started
        self.assertNotIn("bank", self.offers())

    def test_savings_once_money_moves_there(self):
        self.add(5000, "2026-11-03", kind="save", payee="")
        self.assertIn("savings", self.offers())
        self.start_balance("savings", 0, "2026-11-01")
        self.assertNotIn("savings", self.offers())


class BudgetFit(AppTest):
    def fit(self, month="2026-11"):
        return api.budget_fit(self.conn, None, None, {"month": [month]})

    def test_budgets_against_income(self):
        self.category("Rent", 90000)
        self.assertEqual((self.fit()["income"], self.fit()["budgets"], self.fit()["income_plans"]), (0, 90000, 0))
        api.set_income(self.conn, None, {"month": "2026-11", "amount": 250000, "name": "Income"}, None)
        fit = self.fit()
        self.assertEqual((fit["income"], fit["left"]), (250000, 160000))
        self.plan("expense", 50000, "2026-11", "2026-11")
        self.assertEqual(self.fit()["left"], 110000)

    def test_changing_the_income_from_a_month_on(self):
        api.set_income(self.conn, None, {"month": "2026-11", "amount": 250000, "name": "Income"}, None)
        plan = self.fit()["plan"]["id"]
        api.set_income(self.conn, None, {"month": "2027-01", "amount": 270000, "plan_id": plan}, None)
        self.assertEqual([self.fit(m)["income"] for m in ("2026-12", "2027-01", "2027-02")], [250000, 270000, 270000])
        api.set_income(self.conn, None, {"month": "2026-10", "amount": 200000, "plan_id": plan}, None)
        self.assertEqual([self.fit(m)["income"] for m in ("2026-10", "2027-01")], [200000, 200000])

    def test_average_spending_helps_choose_amounts(self):
        self.add(10000, "2026-09-02")
        self.add(30000, "2026-10-02")
        self.assertEqual(self.fit()["spending"], {"months": 2, "average": 20000})


class StarterBudgets(AppTest):
    def test_added_together_or_not_at_all(self):
        api.add_starter_budgets(self.conn, None, {"month": "2026-11", "budgets": [{"name": "Rent", "budget": 90000}, {"name": "Food", "budget": 30000}]}, None)
        self.assertEqual(self.month("2026-11")["totals"]["budget"], 120000)
        with self.assertRaises(ApiError):
            api.add_starter_budgets(self.conn, None, {"month": "2026-11", "budgets": []}, None)
        with self.assertRaises(ApiError):
            api.add_starter_budgets(self.conn, None, {"month": "2026-11", "budgets": [{"name": "Rent", "budget": 1000}]}, None)

    def test_a_category_with_items(self):
        api.add_starter_budgets(self.conn, None, {"month": "2026-11", "budgets": [
            {"name": "Fixed costs", "items": [{"name": "Rent", "budget": 90000}, {"name": "Energy", "budget": 12000}]},
            {"name": "Empty", "items": []},  # no item filled in: no category
            {"name": "Groceries", "budget": 30000}]}, None)
        groups = {g["name"]: [l["name"] for l in g["lines"]] for g in self.month("2026-11")["groups"]}
        self.assertEqual(groups, {"Fixed costs": ["Rent", "Energy"], "Groceries": [None]})
        self.assertEqual(self.month("2026-11")["totals"]["budget"], 132000)
