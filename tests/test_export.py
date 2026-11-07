"""Exporting transactions as CSV."""
from app import api, export

from .base import AppTest


class TransactionsCsv(AppTest):
    def setUp(self):
        super().setUp()
        cat = self.category("Groceries")
        self.food = self.item(cat, "Food", 30000)
        self.home = self.item(cat, "Household", 5000)
        api.save_transaction(self.conn, None, {"amount": 4831, "date": "2026-11-07", "kind": "expense", "payee": "=Shop",
                                               "splits": [{"item_id": int(self.food[1:]), "amount": 4632},
                                                          {"item_id": int(self.home[1:]), "amount": 199}]}, None)
        self.add(250000, "2026-11-01", kind="income", payee="Employer")
        self.add(1000, "2026-10-31")

    def rows(self, month="2026-11", decimal="."):
        name, data = export.transactions_csv(self.conn, month, decimal)
        return name, data.decode("utf-8-sig").splitlines()

    def test_a_row_per_part_oldest_first_signed_from_the_bank(self):
        name, rows = self.rows()
        self.assertEqual(name, "Budget transactions 2026-11.csv")
        self.assertEqual(rows[1:], [
            "2026-11-01,2026-11-01,Income,Employer,,,,2500.00,2500.00",
            "2026-11-07,2026-11-07,Expense,'=Shop,,Groceries,Food,-46.32,-48.31",
            "2026-11-07,2026-11-07,Expense,'=Shop,,Groceries,Household,-1.99,-48.31",
        ])

    def test_decimal_comma_uses_semicolons_and_all_months(self):
        _, rows = self.rows("", ",")
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[1], "2026-10-31;2026-10-31;Expense;Shop;;;;-10,00;-10,00")

    def test_only_the_chosen_transactions(self):
        ids = {r["id"] for r in self.conn.execute("SELECT id FROM expenses WHERE payee = 'Employer'")}
        name, data = export.transactions_csv(self.conn, "", ".", ids)
        self.assertEqual(name, "Budget transactions (1).csv")
        self.assertEqual(data.decode("utf-8-sig").splitlines()[1:], ["2026-11-01,2026-11-01,Income,Employer,,,,2500.00,2500.00"])
