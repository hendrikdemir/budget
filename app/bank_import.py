"""Reading bank exports (CSV files) into transactions to review before they're added.

Each bank has a reader in READERS: `name`, `matches(header)` (does this file come from that
bank?) and `read(rows)`, which turns the rows after the header into transactions:
{date, paid_date, amount (cents), kind, payee, description}. `date` is when you paid (e.g.
at the till), `paid_date` when the money left the bank, if that was another day. To support
another bank, write a reader like IngReader and add it to READERS. A reader may also give
`parts`: [{category, item, amount}], the budgets by name (BudgetReader, for Budget's own
exports); preview() turns them into budget lines.

`preview()` adds suggestions from what's already in Budget: the known payee name and the
budget it was last booked on, and transactions that look like they were added already.
"""
import csv
import io
import re
from datetime import date, timedelta

from .budgets import categories_for
from .money import ApiError


def cents(text):
    """Bank amounts like "1.234,56" or "1234.56" as whole cents."""
    t = text.strip().replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    whole, _, part = t.lstrip("-").partition(".")
    if not whole.isdigit() or (part and not part.isdigit()):
        raise ValueError(text)
    return int(whole) * 100 + int((part + "00")[:2])


def tidy_name(name):
    """Names from card terminals are often in capitals: "CORNER GROCER 0042" -> "Corner Grocer 0042"."""
    name = re.sub(r"\s+", " ", name).strip()
    return name.title() if name.isupper() else name


class IngReader:
    """ING (Netherlands). Columns: Datum, Naam / Omschrijving, Rekening, Tegenrekening, Code,
    Af Bij, Bedrag (EUR), Mutatiesoort, Mededelingen (newer exports add Saldo na mutatie, Tag)."""
    name = "ING"
    columns = ("Datum", "Naam / Omschrijving", "Af Bij", "Bedrag (EUR)", "Mededelingen")

    def matches(self, header):
        return all(c in header for c in self.columns)

    def read(self, rows):
        found = []
        for row in rows:
            booked = self.day(row["Datum"])
            notes = row.get("Mededelingen", "")
            name = row["Naam / Omschrijving"]
            out = row["Af Bij"].strip().lower() == "af"
            card = row.get("Code") == "BA" or row.get("Mutatiesoort") == "Betaalautomaat"
            # A card payment says when you paid: "Datum: 31-10-2026" (booked the next day).
            paid_on = re.search(r"\bDatum: (\d{2})-(\d{2})-(\d{4})", notes) if card else None
            day = f"{paid_on[3]}-{paid_on[2]}-{paid_on[1]}" if paid_on else booked
            savings = "spaarrekening" in name.lower() or re.match(r"(Naar|Van) .*spaarrekening", notes, re.I)
            if savings:
                kind = "save" if out else "withdraw"
            else:
                kind = "expense" if out else "income"
            if card:
                # "BCK*CORNER GROCER 0042 NLD": drop the payment provider and the country.
                name = re.sub(r"^[A-Z0-9]{2,6}\s?\*\s*", "", name)
                name = re.sub(r"\s+[A-Z]{3}$", "", name)
            described = re.search(r"Omschrijving: (.*?)\s*(?:IBAN:|Kenmerk:|Machtiging ID:|Valutadatum:|$)", notes)
            found.append({
                "date": day,
                "paid_date": booked if booked != day else None,
                "amount": cents(row["Bedrag (EUR)"]),
                "kind": kind,
                "payee": "" if savings else tidy_name(name),
                "description": described[1].strip() if described and not card else "",
            })
        return found

    @staticmethod
    def day(text):
        t = text.strip()
        return f"{t[:4]}-{t[4:6]}-{t[6:8]}" if re.fullmatch(r"\d{8}", t) else t


class BudgetReader:
    """Budget's own CSV export (app/export.py): a row per part of a transaction, with the
    budget by name. Rows of one transaction follow each other and share everything but
    Category, Item and Amount."""
    name = "Budget"
    columns = ("Date", "Left bank", "Type", "Payee", "Note", "Category", "Item", "Amount", "Total")
    KINDS = {"Expense": "expense", "Income": "income", "To savings": "save", "From savings": "withdraw"}

    def matches(self, header):
        return all(c in header for c in self.columns)

    @staticmethod
    def text(value):
        """Undo the export's guard against spreadsheet formulas: "'=Shop" -> "=Shop"."""
        value = (value or "").strip()
        return value[1:] if value[:1] == "'" and value[1:2] in ("=", "+", "-", "@") else value

    def read(self, rows):
        found, last, rest = [], None, 0
        for row in rows:
            same = ("Date", "Left bank", "Type", "Payee", "Note", "Total")
            key = tuple(row[c] for c in same)
            # A transaction's rows add up to its total: once they do, the next row starts a new
            # one, even if it looks the same (two coffees at the same place on one day).
            if key != last or rest <= 0:
                day, left = row["Date"].strip(), row["Left bank"].strip()
                date.fromisoformat(day)  # a ValueError for anything else
                found.append({"date": day, "paid_date": left if left and left != day else None,
                              "amount": cents(row["Total"]), "kind": self.KINDS[row["Type"].strip()],
                              "payee": self.text(row["Payee"]), "description": self.text(row["Note"]), "parts": []})
                last, rest = key, found[-1]["amount"]
            amount = cents(row["Amount"]) if (row["Amount"] or "").strip() else rest
            rest -= amount
            category = self.text(row["Category"])
            if category:
                found[-1]["parts"].append({"category": category, "item": self.text(row["Item"]), "amount": amount})
        return found


READERS = [IngReader(), BudgetReader()]


def read_file(data):
    """The bank and transactions in an exported file (bytes)."""
    text = data.decode("utf-8-sig", errors="replace") if isinstance(data, bytes) else data
    sample = text[:2000]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.DictReader(io.StringIO(text), delimiter=delimiter))
    header = rows[0].keys() if rows else next(csv.reader(io.StringIO(text), delimiter=delimiter), [])
    reader = next((r for r in READERS if r.matches(list(header))), None)
    if not reader:
        names = ", ".join(r.name for r in READERS)
        raise ApiError(f"This file isn't a bank export Budget can read. It can read exports from {names} (CSV).")
    try:
        transactions = reader.read(rows)
    except (KeyError, ValueError, TypeError):
        raise ApiError(f"This {reader.name} file has something Budget doesn't understand, so nothing was read. "
                       "Export it again as CSV and try once more.")
    if not transactions:
        raise ApiError("This file has no transactions in it.")
    return reader.name, transactions


def simple(name):
    """Name without numbers or punctuation, to compare payees: "Corner Grocer 0042" -> "corner grocer"."""
    return " ".join(re.sub(r"[^a-z ]", " ", name.lower()).split())


def preview(conn, data, known_payees):
    """The transactions in a bank file, with suggestions, and the budget lines to choose from."""
    bank, found = read_file(data)

    # The payee as you named it before, and the budget it was last booked on.
    known = [(simple(p["name"]), p) for p in known_payees if simple(p["name"])]
    for t in found:
        if not t["payee"] or "parts" in t:  # a Budget export already has its own names and budgets
            continue
        mine = simple(t["payee"])
        matches = [p for s, p in known if p["kind"] == t["kind"] and len(min(s, mine, key=len)) >= 4
                   and (mine.startswith(s) or s.startswith(mine))]
        if matches:
            best = max(matches, key=lambda p: len(simple(p["name"])))
            t["payee"], t["line"] = best["name"], best["line"]

    # Already in Budget: the same kind and amount, within a few days. Each match is used once.
    used = set()
    for t in found:
        days = [d for d in (t["date"], t["paid_date"]) if d]
        start = (date.fromisoformat(min(days)) - timedelta(days=3)).isoformat()
        end = (date.fromisoformat(max(days)) + timedelta(days=3)).isoformat()
        for r in conn.execute(
            "SELECT id, date, payee FROM expenses WHERE kind = ? AND amount_cents = ? AND "
            "(date BETWEEN ? AND ? OR paid_date BETWEEN ? AND ?) ORDER BY ABS(julianday(date) - julianday(?))",
            (t["kind"], t["amount"], start, end, start, end, t["date"]),
        ):
            if r["id"] not in used:
                used.add(r["id"])
                t["duplicate"] = {"date": r["date"], "payee": r["payee"]}
                break

    # Budget lines of every month in the file, for choosing a budget per transaction.
    lines = {}
    for month in sorted({t["date"][:7] for t in found}):
        for c in categories_for(conn, month):
            for item in c["items"]:
                if item["budget"] is not None:
                    lines[f"i{item['id']}"] = {"value": f"i{item['id']}", "label": item["name"], "group": c["name"]}
            if c["single"]:
                lines[f"c{c['id']}"] = {"value": f"c{c['id']}", "label": c["name"]}
    # Budgets by name (from a Budget export): one covering the whole amount is chosen like a
    # suggestion; a split is kept as it is. A budget that doesn't exist here is left out.
    by_name = {(l.get("group") or l["label"], l["label"] if l.get("group") else ""): l for l in lines.values()}
    for t in found:
        parts = t.pop("parts", None)
        if not parts:
            continue
        known = [(by_name.get((p["category"], p["item"])), p) for p in parts]
        t["missing"] = [f"{p['category']} · {p['item']}" if p["item"] else p["category"] for l, p in known if not l]
        known = [(l, p) for l, p in known if l]
        if len(known) == 1 and known[0][1]["amount"] == t["amount"]:
            t["line"] = known[0][0]["value"]
        elif known:
            t["splits"] = [{"line": l["value"], "label": f"{l['group']} · {l['label']}" if l.get("group") else l["label"],
                            "amount": p["amount"]} for l, p in known]
    for t in found:
        if t.get("line") not in lines:
            t["line"] = None
    ordered = sorted(lines.values(), key=lambda l: (l.get("group") or l["label"], "group" in l, l["label"]))
    return {"bank": bank, "transactions": found, "lines": ordered}
