"""Exporting all data to one file, and importing such a file (for example on a new Mac).

An export is a copy of the SQLite database, with the extension .budget. An import first
checks the file thoroughly, then keeps a safety copy of the current data so it can be undone.
Deleting all data keeps a safety copy the same way.
"""
import sqlite3
import tempfile
from datetime import date, datetime
from pathlib import Path

from . import db
from .money import ApiError

MAX_SIZE = 200 * 1024 * 1024
KEEP_SAFETY_COPIES = 5
KEEP_SETTINGS = ("theme", "currency")  # how Budget looks stays when all data is deleted
REQUIRED_TABLES = {"categories", "items", "budgets", "expenses", "splits", "settings"}
NOT_A_BACKUP = "This isn't a Budget backup. Choose a file that ends in .budget, made with Export data."
DAMAGED = "This backup file is damaged, so it can't be imported. Your data hasn't changed. Try exporting it again."
TOO_NEW = "This backup was made with a newer version of Budget. Update Budget, then import it again. Your data hasn't changed."


def export_file():
    """The file name and contents of an export of all data."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "export.budget"
        source, copy = db.connect(), sqlite3.connect(path)
        try:
            source.backup(copy)
        finally:
            copy.close()
            source.close()
        return f"Budget backup {date.today().isoformat()}.budget", path.read_bytes()


def summary(conn):
    dates = conn.execute("SELECT MIN(date) AS first, MAX(date) AS last, COUNT(*) AS n FROM expenses").fetchone()
    return {"transactions": dates[2], "first_date": dates[0], "last_date": dates[1],
            "categories": conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]}


def inspect(path):
    """Checks that the file is an undamaged Budget backup this version can read, and
    returns what's in it. Raises a friendly ApiError otherwise."""
    with open(path, "rb") as f:
        if f.read(16) != b"SQLite format 3\x00":
            raise ApiError(NOT_A_BACKUP)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        try:
            objects = conn.execute("SELECT type, name FROM sqlite_master").fetchall()
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            healthy = conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        except sqlite3.DatabaseError:
            raise ApiError(DAMAGED)
        if not healthy:
            raise ApiError(DAMAGED)
        # Our exports hold only tables and indexes, never anything that can run by itself.
        if not REQUIRED_TABLES <= {name for kind, name in objects if kind == "table"} \
                or any(kind in ("trigger", "view") for kind, _ in objects) or version < 1:
            raise ApiError(NOT_A_BACKUP)
        if version > len(db.MIGRATIONS):
            raise ApiError(TOO_NEW)
        try:
            return summary(conn)
        except sqlite3.DatabaseError:
            raise ApiError(NOT_A_BACKUP)
    finally:
        conn.close()


def _with_temp_file(data, action):
    if not data or len(data) > MAX_SIZE:
        raise ApiError(NOT_A_BACKUP)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "import.budget"
        path.write_bytes(data)
        return action(path)


def _replace_data_with(path):
    source, target = sqlite3.connect(f"file:{path}?mode=ro", uri=True), db.connect()
    try:
        source.backup(target)  # all or nothing
    finally:
        target.close()
        source.close()
    db.migrate()


def _safety_copies():
    """Copies of the data from before an import or a delete, oldest first."""
    return sorted(db.BACKUP_DIR.glob("before-*.db"), key=lambda p: p.name.split("-", 2)[-1])


def _keep_safety_copy(reason):
    db.BACKUP_DIR.mkdir(exist_ok=True)
    safety = db.BACKUP_DIR / f"before-{reason}-{datetime.now():%Y-%m-%d-%H%M%S}.db"
    source, copy = db.connect(), sqlite3.connect(safety)
    try:
        source.backup(copy)
    finally:
        copy.close()
        source.close()
    for old in _safety_copies()[:-KEEP_SAFETY_COPIES]:
        old.unlink()


def check(data):
    """What's in a backup, compared to the current data."""
    backup = _with_temp_file(data, inspect)
    return {"backup": backup, "current": inspect_current()}


def restore(data):
    """Replaces all data with a backup, after keeping a safety copy of the current data."""
    def run(path):
        inspect(path)
        _keep_safety_copy("import")
        _replace_data_with(path)
        return inspect_current()
    return _with_temp_file(data, run)


def inspect_current():
    conn = db.connect()
    try:
        return summary(conn)
    finally:
        conn.close()


def clear():
    """Deletes all transactions, budgets, plans and balances, keeping how Budget looks.
    A safety copy is kept first, so it can be undone."""
    _keep_safety_copy("delete")
    conn = db.connect()
    try:
        conn.execute("PRAGMA foreign_keys = OFF")  # everything goes, so the order doesn't matter
        with conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
            for table in tables:
                if table == "settings":
                    conn.execute(f"DELETE FROM settings WHERE key NOT IN ({','.join('?' * len(KEEP_SETTINGS))})", KEEP_SETTINGS)
                else:
                    conn.execute(f'DELETE FROM "{table}"')
    finally:
        conn.close()
    return inspect_current()


def status():
    """Whether the last import or delete can be undone, and which it was."""
    copies = _safety_copies()
    return {"can_undo": bool(copies), "last": copies[-1].name.split("-")[1] if copies else None}


def undo():
    """Puts back the data from before the last import or delete."""
    copies = _safety_copies()
    if not copies:
        raise ApiError("There's nothing to undo.")
    _replace_data_with(copies[-1])
    copies[-1].unlink()
    return inspect_current()
