"""Exporting all data to one file, and importing such a file (for example on a new Mac).

An export is a copy of the SQLite database, with the extension .budget. An import first
checks the file thoroughly, then replaces all data with it; the page offers to create a backup
of the current data first. Deleting all data is final: it also removes the automatic backups,
so nothing of the old data stays behind.
"""
import sqlite3
import tempfile
from datetime import date
from pathlib import Path

from . import db
from .money import ApiError

MAX_SIZE = 200 * 1024 * 1024
KEEP_SETTINGS = ("theme", "currency")  # how Budget looks stays when all data is deleted
REQUIRED_TABLES = {"categories", "items", "budgets", "expenses", "splits", "settings"}
NOT_A_BACKUP = "This isn't a Budget backup. Choose a file that ends in .budget, made with Create backup."
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


def check(data):
    """What's in a backup, compared to the current data."""
    backup = _with_temp_file(data, inspect)
    return {"backup": backup, "current": inspect_current()}


def restore(data):
    """Replaces all data with a backup."""
    def run(path):
        inspect(path)
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
    """Deletes all transactions, budgets, plans and balances, keeping how Budget looks. This
    can't be undone: the automatic backups go too."""
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
    if db.BACKUP_DIR.exists():
        for copy in db.BACKUP_DIR.glob("*.db"):
            copy.unlink()
    return inspect_current()
