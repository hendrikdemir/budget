"""Budgets: history "from a month onward", carry-over, totals and transactions."""
from app import api
from app.money import ApiError

from .base import AppTest


class BudgetHistory(AppTest):
    def test_a_change_applies_from_its_month_onward(self):
        food = self.item(self.category("Groceries"), "Food", 30000)
        self.change(food, "2026-03", 35000)
        self.assertEqual(self.line("2026-02", food)["budget"], 30000)
        self.assertEqual(self.line("2026-03", food)["budget"], 35000)
        self.assertEqual(self.line("2026-09", food)["budget"], 35000)

    def test_an_ended_budget_disappears_from_then_on_only(self):
        home = self.category("Home")
        rent = self.item(home, "Rent", 95000)
        self.add(95000, "2026-02-01", rent)
        api.remove_item(self.conn, int(rent[1:]), None, {"month": ["2026-04"]})
        self.assertEqual(self.line("2026-03", rent)["budget"], 95000)
        self.assertFalse(any(l["key"] == rent for g in self.month("2026-04")["groups"] for l in g["lines"]))


class CarryOver(AppTest):
    def test_leftover_carries_over_when_set(self):
        fun = self.item(self.category("Fun"), "Fun money", 10000, carry=True)
        self.add(3000, "2026-01-10", fun)
        self.assertEqual(self.line("2026-02", fun)["carried_in"], 7000)
        self.assertEqual(self.line("2026-02", fun)["available"], 17000)

    def test_leftover_stays_behind_by_default(self):
        food = self.item(self.category("Groceries"), "Food", 30000)
        self.add(10000, "2026-01-10", food)
        self.assertEqual(self.line("2026-02", food)["carried_in"], 0)

    def test_a_choice_for_one_month_overrides_the_default(self):
        food = self.item(self.category("Groceries"), "Food", 30000)
        self.add(10000, "2026-01-10", food)
        api.choose_rollover(self.conn, None, {"item_id": int(food[1:]), "month": "2026-01", "carry": True}, None)
        self.assertEqual(self.line("2026-02", food)["carried_in"], 20000)
        self.assertEqual(self.line("2026-03", food)["carried_in"], 0)  # February's leftover stays behind again

    def test_the_order_months_are_asked_in_doesnt_matter(self):
        fun = self.item(self.category("Fun"), "Fun money", 10000, carry=True)
        for month, spent in (("01", 3000), ("02", 12000), ("03", 1000), ("05", 4000)):
            self.add(spent, f"2026-{month}-10", fun)
        expected = {"2026-02": 7000, "2026-03": 5000, "2026-04": 14000, "2026-05": 24000, "2026-06": 30000}
        for month in ("2026-06", "2026-02", "2026-05", "2026-03", "2026-04", "2026-01"):
            self.assertEqual(self.line(month, fun)["carried_in"], expected.get(month, 0))

    def test_a_change_after_asking_is_taken_into_account(self):
        fun = self.item(self.category("Fun"), "Fun money", 10000, carry=True)
        self.assertEqual(self.line("2026-03", fun)["carried_in"], 20000)
        self.add(4000, "2026-01-10", fun)  # through the same connection, so the remembered results go
        self.assertEqual(self.line("2026-03", fun)["carried_in"], 16000)
        self.assertEqual(self.line("2026-01", fun)["spent"], 4000)

    def test_overspending_doesnt_carry_a_negative_amount(self):
        fun = self.item(self.category("Fun"), "Fun money", 10000, carry=True)
        self.add(15000, "2026-01-10", fun)
        self.assertEqual(self.line("2026-02", fun)["carried_in"], 0)


class Totals(AppTest):
    def test_spending_inside_and_outside_budgets(self):
        food = self.item(self.category("Groceries"), "Food", 30000)
        self.add(12000, "2026-11-02", food)
        self.add(4000, "2026-11-03")  # no budget
        totals = self.month("2026-11")["totals"]
        self.assertEqual((totals["spent"], totals["budget_spent"], totals["outside"]), (16000, 12000, 4000))

    def test_income_can_top_up_a_budget(self):
        fun = self.item(self.category("Fun"), "Fun money", 10000)
        self.add(2500, "2026-11-05", fun, kind="income", payee="Marketplace")
        self.assertEqual(self.line("2026-11", fun)["available"], 12500)

    def test_a_finished_month_counts_money_moved_to_savings_as_its_leftover(self):
        food = self.item(self.category("Groceries"), "Food", 30000)
        self.add(10000, "2026-10-10", food)
        self.add(15000, "2026-10-31", kind="save")
        leftover = self.month("2026-10")["leftover"]
        self.assertEqual((leftover["unspent"], leftover["rest"]), (20000, 5000))
        # Taking money from savings isn't unspent budget.
        self.add(50000, "2026-10-31", kind="withdraw")
        self.assertEqual(self.month("2026-10")["leftover"]["rest"], 20000)

    def test_the_current_month_keeps_all_unspent_budget_spendable(self):
        food = self.item(self.category("Groceries"), "Food", 30000)
        self.add(15000, "2026-11-01", kind="save")
        self.assertEqual(self.month("2026-11")["leftover"]["rest"], 30000)

    def test_review_figures_of_a_finished_month(self):
        fun = self.item(self.category("Fun", month="2026-10"), "Fun money", 10000, month="2026-10", carry=True)
        self.add(4000, "2026-10-10", fun)
        self.add(250000, "2026-10-25", kind="income", payee="Employer")
        totals = self.month("2026-10")["totals"]
        self.assertEqual((totals["net"], totals["carried_out"]), (246000, 6000))


class Transactions(AppTest):
    def test_parts_cant_add_up_to_more_than_the_amount(self):
        food = self.item(self.category("Groceries"), "Food", 30000)
        with self.assertRaises(ApiError):
            api.save_transaction(self.conn, None, {"amount": 1000, "date": "2026-11-01", "payee": "Shop",
                                                   "splits": [{"item_id": int(food[1:]), "amount": 1500}]}, None)

    def test_an_expense_needs_a_payee_but_a_transfer_doesnt(self):
        with self.assertRaises(ApiError):
            self.add(1000, "2026-11-01", payee="")
        self.add(1000, "2026-11-01", kind="save", payee="")

    def test_a_paid_date_on_the_same_day_isnt_stored(self):
        self.add(1000, "2026-11-01", paid_date="2026-11-01")
        self.assertIsNone(self.month("2026-11")["transactions"][0]["paid_date"])
