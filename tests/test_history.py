"""Looking back: a year's months, totals and balances."""
from app import accounts, budgets

from .base import AppTest


class YearHistory(AppTest):
    TODAY = "2026-03-15"

    def setUp(self):
        super().setUp()
        self.start_balance("bank", 100000, "2026-02-01")
        self.start_balance("savings", 500000, "2026-02-01")
        self.add(5000, "2026-01-20")  # before tracking started
        self.add(250000, "2026-02-25", kind="income", payee="Employer")
        self.add(80000, "2026-02-10")
        self.add(30000, "2026-03-01", kind="save")

    def test_only_finished_months(self):
        h = accounts.year_history(self.conn, 2026)
        self.assertEqual([m["month"] for m in h["months"]], ["2026-02"])

    def test_income_spending_and_result(self):
        feb = accounts.year_history(self.conn, 2026)["months"][0]
        self.assertEqual((feb["income"], feb["spent"], feb["net"]), (250000, 80000, 170000))

    def test_balances_from_the_starting_point_on(self):
        feb, = accounts.year_history(self.conn, 2026)["months"]
        self.assertEqual((feb["bank"], feb["savings"]), (270000, 500000))

    def test_the_current_month_counts_once_it_is_over(self):
        self.on("2026-04-01")
        mar = accounts.year_history(self.conn, 2026)["months"][-1]
        self.assertEqual((mar["month"], mar["bank"], mar["savings"]), ("2026-03", 240000, 530000))  # the transfer moved money over

    def test_totals_and_years(self):
        h = accounts.year_history(self.conn, 2026)
        self.assertEqual((h["totals"]["spent"], h["totals"]["savings_change"], h["totals"]["bank_change"]), (80000, 0, 170000))
        self.assertEqual((h["first_year"], h["last_year"]), (2026, 2026))

    def test_without_a_starting_point_every_month_counts(self):
        self.conn.execute("DELETE FROM settings WHERE key LIKE '%_start_%'")
        h = accounts.year_history(self.conn, 2026)
        self.assertEqual([m["month"] for m in h["months"]], ["2026-01", "2026-02"])

    def test_without_a_starting_point_it_starts_at_the_first_transaction(self):
        self.conn.execute("DELETE FROM settings WHERE key LIKE '%_start_%'")
        self.conn.execute("DELETE FROM expenses WHERE date < '2026-02-01'")
        h = accounts.year_history(self.conn, 2026)
        self.assertEqual(([m["month"] for m in h["months"]], h["empty"]), (["2026-02"], False))

    def test_nothing_added_yet(self):
        self.conn.execute("DELETE FROM settings")
        self.conn.execute("DELETE FROM expenses")
        h = accounts.year_history(self.conn, 2026)
        self.assertEqual((h["months"], h["empty"], h["first_year"], h["last_year"]), ([], True, 2026, 2026))
        self.assertEqual(budgets.budget_history(self.conn, 2026)["groups"], [])

    def test_a_year_before_tracking(self):
        h = accounts.year_history(self.conn, 2025)
        self.assertEqual(h["months"], [])
        self.assertIsNone(h["totals"]["savings_change"])


class BudgetHistory(AppTest):
    TODAY = "2026-05-15"

    def setUp(self):
        super().setUp()
        cat = self.category("Groceries")
        self.food = self.item(cat, "Food", 30000)
        self.fun = self.category("Fun money", 10000)
        for month, spent in (("01", 32000), ("02", 31000), ("03", 25000), ("04", 30500)):
            self.add(spent, f"2026-{month}-10", self.food)
            self.add(2000, f"2026-{month}-11", f"c{self.fun}")

    def line(self, key):
        h = budgets.budget_history(self.conn, 2026)
        return next(l for g in h["groups"] for l in g["lines"] if l["key"] == key), h

    def test_finished_months_with_budget_and_spending(self):
        food, h = self.line(self.food)
        self.assertEqual(h["months"], ["2026-01", "2026-02", "2026-03", "2026-04"])
        self.assertEqual((food["budget"], food["spent"], food["budgeted_months"]), (120000, 118500, 4))
        self.assertEqual(food["months"]["2026-02"], {"budget": 30000, "available": 30000, "spent": 31000})

    def test_structurally_over_and_under(self):
        food, _ = self.line(self.food)
        self.assertEqual((food["over_budget"], food["pattern"]), (3, None))  # over 3 of 4 months, but not in total
        self.add(5000, "2026-03-20", self.food)
        food, _ = self.line(self.food)
        self.assertEqual(food["pattern"], "over")
        fun, _ = self.line(f"c{self.fun}")
        self.assertEqual((fun["over_budget"], fun["pattern"]), (0, "under"))

    def test_spending_outside_budgets(self):
        self.add(1500, "2026-02-12")
        self.add(500, "2026-02-20")
        outside = budgets.budget_history(self.conn, 2026)["outside"]
        self.assertEqual((outside["spent"], outside["budgeted_months"], outside["pattern"]), (2000, 0, None))
        self.assertEqual(list(outside["months"]), ["2026-02"])
