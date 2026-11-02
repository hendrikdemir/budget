"""Looking ahead: "ready for next month?" and the savings projection."""
from app import outlook

from .base import AppTest


class ReadyForNextMonth(AppTest):
    """November: a 1,000 budget, fully spent. December needs 1,000 too."""
    TODAY = "2026-11-28"

    def setUp(self):
        super().setUp()
        self.living = self.category("Living", 100000)
        self.add(100000, "2026-11-05", f"c{self.living}")
        self.start_balance("bank", 150000, "2026-11-01")
        self.start_balance("savings", 500000, "2026-11-01")

    def ready(self, month="2026-11"):
        return outlook.month_outlook(self.conn, month, self.month(month))

    def test_short_when_the_bank_holds_less_than_next_month_needs(self):
        o = self.ready()
        self.assertEqual((o["balance"], o["needed"], o["short"], o["spare"]), (50000, 100000, 50000, 0))

    def test_spare_when_it_holds_more(self):
        self.add(80000, "2026-11-20", kind="income", payee="Employer")
        o = self.ready()
        self.assertEqual((o["short"], o["spare"]), (0, 30000))

    def test_income_still_expected_this_month_counts(self):
        self.plan("income", 30000, "2026-11")
        o = self.ready()
        self.assertEqual((o["expected_income"], o["short"]), (30000, 20000))

    def test_income_already_received_lowers_what_is_still_expected(self):
        self.plan("income", 30000, "2026-11")
        self.add(10000, "2026-11-20", kind="income", payee="Employer")
        self.assertEqual(self.ready()["expected_income"], 20000)

    def test_bills_paid_before_the_month_lower_what_it_needs(self):
        self.add(20000, "2026-12-01", f"c{self.living}", paid_date="2026-11-27")
        o = self.ready()
        self.assertEqual((o["prepaid"], o["needed"]), (20000, 80000))

    def test_too_early_until_the_last_week(self):
        self.on("2026-11-23")
        self.assertTrue(self.ready()["too_early"])
        self.on("2026-11-24")
        self.assertFalse(self.ready()["too_early"])

    def test_only_for_the_current_month(self):
        self.assertEqual(self.ready("2026-12")["when"], "future")
        self.on("2026-12-02")
        self.assertEqual(self.ready("2026-11")["when"], "past")


class Projection(AppTest):
    TODAY = "2026-11-15"

    def setUp(self):
        super().setUp()
        self.category("Living", 100000)
        self.start_balance("bank", 100000, "2026-11-01")
        self.start_balance("savings", 500000, "2026-11-01")
        self.plan("income", 150000, "2026-11")
        self.plan("expense", 400000, "2027-03", "2027-03", name="Holiday")

    def test_the_layers_add_up_and_free_to_spend_looks_ahead(self):
        p = outlook.projection(self.conn)
        rows = p["rows"]
        for i, r in enumerate(rows):
            if r["above"] >= 0:
                self.assertEqual(r["free"] + r["later"] + r["buffer"], r["savings"], r["month"])
            # Free to spend never takes more than any later month can miss.
            self.assertTrue(all(r["free"] <= max(0, later["above"]) for later in rows[i:]), r["month"])
        self.assertEqual(p["low_month"], "2027-03")  # the holiday is the dip

    def test_income_still_expected_this_month_counts_now(self):
        first = outlook.projection(self.conn)["rows"][0]
        self.assertEqual(first["income"], 150000)

    def test_hidden_without_starting_balances(self):
        self.conn.execute("DELETE FROM settings WHERE key LIKE 'savings_%'")
        self.assertFalse(outlook.projection(self.conn)["visible"])
