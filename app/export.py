"""Exporting transactions as a CSV file, for a spreadsheet."""
import csv
import io

from . import budgets

KINDS = {"expense": "Expense", "income": "Income", "save": "To savings", "withdraw": "From savings"}
# Seen from the bank account: what comes in is positive, what goes out negative.
SIGN = {"expense": -1, "income": 1, "save": -1, "withdraw": 1}


def transactions_csv(conn, month="", decimal=".", ids=None):
    """The file name and contents of a CSV of the transactions in `month` ("" = all), oldest
    first; with `ids`, only those. A transaction split over budgets gets a row per part (and one for the rest outside a
    budget), so a spreadsheet can total per budget; "Total" repeats the whole amount. With a
    decimal comma, values are separated by semicolons, as spreadsheets in those locales expect."""
    comma = decimal == ","
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";" if comma else ",", lineterminator="\r\n")
    writer.writerow(["Date", "Left bank", "Type", "Payee", "Note", "Category", "Item", "Amount", "Total"])

    def amount(cents):
        text = f"{'-' if cents < 0 else ''}{abs(cents) // 100}.{abs(cents) % 100:02d}"
        return text.replace(".", ",") if comma else text

    def text(value):
        """Text a spreadsheet would run as a formula (from a bank export, say) is kept as text."""
        value = value or ""
        return f"'{value}" if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value

    chosen = [t for t in budgets.transactions(conn, month) if ids is None or t["id"] in ids]
    for t in reversed(chosen):
        sign = SIGN[t["kind"]]
        parts = [(s["category"], s["item"] or "", s["amount"]) for s in t["splits"]]
        rest = t["amount"] - sum(p[2] for p in parts)
        if rest or not parts:
            parts.append(("", "", rest))
        for category, item, cents in parts:
            writer.writerow([t["date"], t["paid_date"] or t["date"], KINDS[t["kind"]], text(t["payee"]), text(t["description"]),
                             text(category), text(item), amount(sign * cents), amount(sign * t["amount"])])
    name = f"Budget transactions {month or 'all'}.csv" if ids is None else f"Budget transactions ({len(chosen)}).csv"
    return name, ("﻿" + out.getvalue()).encode()  # the BOM makes Excel read it as UTF-8
