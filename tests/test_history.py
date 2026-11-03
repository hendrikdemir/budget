"""Looking back: a year's months, totals and balances."""
from app import accounts

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

    def test_a_year_before_tracking(self):
        h = accounts.year_history(self.conn, 2025)
        self.assertEqual(h["months"], [])
        self.assertIsNone(h["totals"]["savings_change"])
