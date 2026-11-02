"""Reading bank exports, suggestions, and adding the reviewed transactions. Made-up data only."""
from app import api, bank_import
from app.money import ApiError

from .base import AppTest

HEADER = '"Datum","Naam / Omschrijving","Rekening","Tegenrekening","Code","Af Bij","Bedrag (EUR)","Mutatiesoort","Mededelingen"'
ROWS = [
    '"20261102","BCK*CORNER GROCER 0042 NLD","NL00INGB0000000000","","BA","Af","12,50","Betaalautomaat",'
    '"Kaartnr: 1234 56** **** 7890 Datum: 01-11-2026 Tijd: 17:42 Apple Pay Valutadatum: 02-11-2026"',
    '"20261101","Oakwood Rentals","NL00INGB0000000000","NL00BANK0123456789","GT","Af","1.234,56","Online bankieren",'
    '"Naam: Oakwood Rentals Omschrijving: Rent November IBAN: NL00BANK0123456789 Valutadatum: 01-11-2026"',
    '"20261101","Oranje Spaarrekening","NL00INGB0000000000","","GT","Bij","100,00","Online bankieren",'
    '"Van Oranje spaarrekening A12345678 Valutadatum: 01-11-2026"',
    '"20261103","Northwind Ltd","NL00INGB0000000000","NL00BANK0000000001","GT","Bij","2.850,00","Online bankieren",'
    '"Naam: Northwind Ltd Omschrijving: Salary IBAN: NL00BANK0000000001"',
]
ING = "\n".join([HEADER, *ROWS]).encode()


class ReadingIng(AppTest):
    def read(self, data=ING):
        bank, found = bank_import.read_file(data)
        self.assertEqual(bank, "ING")
        return found

    def test_a_card_payment(self):
        t = self.read()[0]
        self.assertEqual((t["date"], t["paid_date"], t["amount"], t["kind"]), ("2026-11-01", "2026-11-02", 1250, "expense"))
        self.assertEqual(t["payee"], "Corner Grocer 0042")  # provider and country dropped, capitals tidied

    def test_a_transfer_with_a_description(self):
        t = self.read()[1]
        self.assertEqual((t["amount"], t["payee"], t["description"], t["paid_date"]), (123456, "Oakwood Rentals", "Rent November", None))

    def test_savings_transfers_and_income(self):
        found = self.read()
        self.assertEqual((found[2]["kind"], found[2]["payee"]), ("withdraw", ""))
        self.assertEqual((found[3]["kind"], found[3]["amount"]), ("income", 285000))

    def test_semicolon_separated_exports(self):
        self.assertEqual(len(self.read(ING.replace(b'","', b'";"'))), 4)

    def test_other_files_are_refused(self):
        with self.assertRaises(ApiError):
            bank_import.read_file(b"date,amount\n2026-11-01,12.50\n")
        with self.assertRaises(ApiError):
            bank_import.read_file(HEADER.encode())  # no transactions


class Suggestions(AppTest):
    def test_known_payee_and_budget(self):
        food = self.item(self.category("Groceries"), "Food", 30000)
        self.add(2000, "2026-10-01", food, payee="Corner Grocer")
        t = api.bank_import_preview(self.conn, None, ING, None)["transactions"][0]
        self.assertEqual((t["payee"], t["line"]), ("Corner Grocer", food))

    def test_each_existing_transaction_is_a_duplicate_only_once(self):
        two = "\n".join([HEADER, ROWS[1], ROWS[1]]).encode()
        self.add(123456, "2026-10-30", payee="Oakwood Rentals")
        found = api.bank_import_preview(self.conn, None, two, None)["transactions"]
        self.assertEqual([bool(t.get("duplicate")) for t in found], [True, False])


class Adding(AppTest):
    def test_all_or_nothing(self):
        good = {"date": "2026-11-01", "amount": 1250, "kind": "expense", "payee": "Corner Grocer", "description": "", "line": None}
        bad = {**good, "payee": ""}
        with self.assertRaises(ApiError):
            api.bank_import_add(self.conn, None, {"transactions": [good, bad]}, None)
        self.conn.rollback()  # what the server does when a request fails
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0], 0)

    def test_a_budget_covers_the_whole_amount(self):
        food = self.item(self.category("Groceries"), "Food", 30000)
        t = {"date": "2026-11-01", "amount": 1250, "kind": "expense", "payee": "Corner Grocer", "description": "", "line": food}
        api.bank_import_add(self.conn, None, {"transactions": [t]}, None)
        self.assertEqual(self.line("2026-11", food)["spent"], 1250)
