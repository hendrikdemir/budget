"""Database connection, schema, migrations and daily backups.

The schema version is stored in SQLite's `user_version`. To change the schema, add a
function to MIGRATIONS; it runs once on databases that are older, in order.
"""
import sqlite3
from datetime import date
from pathlib import Path

# Where the data lives: this folder by default; the Mac app calls use_data_dir().
DB_PATH = Path(__file__).resolve().parent.parent / "budget.db"
BACKUP_DIR = DB_PATH.parent / "backups"
KEEP_BACKUPS = 14  # days

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    UNIQUE (category_id, name)
);
CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,  -- set for category-level budgets
    item_id INTEGER REFERENCES items(id) ON DELETE CASCADE,           -- set for item budgets
    start_month TEXT NOT NULL,   -- YYYY-MM
    amount_cents INTEGER,        -- NULL = ended from this month
    rollover INTEGER NOT NULL DEFAULT 0  -- carry leftovers to the next month by default
);
CREATE TABLE IF NOT EXISTS rollover_choices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    item_id INTEGER REFERENCES items(id) ON DELETE CASCADE,
    month TEXT NOT NULL,          -- the month whose leftover this decides
    carry INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,            -- YYYY-MM-DD; decides the budget month
    amount_cents INTEGER NOT NULL,
    payee TEXT NOT NULL DEFAULT '',   -- who was paid, or for income: who paid
    description TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'expense',  -- 'expense', 'income', 'save' or 'withdraw'
    paid_date TEXT  -- YYYY-MM-DD the money actually moved, when not on `date` (e.g. paid in advance)
);
CREATE TABLE IF NOT EXISTS splits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    item_id INTEGER REFERENCES items(id),  -- NULL when booked on the category itself
    amount_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS balance_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT NOT NULL DEFAULT 'bank',  -- 'bank' or 'savings'
    date TEXT NOT NULL,           -- YYYY-MM-DD; the balance at the end of this day
    amount_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,            -- 'income' or 'expense'
    name TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    start_month TEXT NOT NULL,     -- YYYY-MM
    end_month TEXT                 -- YYYY-MM, inclusive; NULL = ongoing
);
CREATE TABLE IF NOT EXISTS plan_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    start_month TEXT NOT NULL,     -- YYYY-MM; the new amount applies from here on
    amount_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
CREATE INDEX IF NOT EXISTS idx_splits_expense ON splits(expense_id);
"""


def use_data_dir(folder):
    global DB_PATH, BACKUP_DIR
    folder.mkdir(parents=True, exist_ok=True)
    DB_PATH = folder / "budget.db"
    BACKUP_DIR = folder / "backups"


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn, table):
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


def _v1_baseline(conn):
    """Version 1: the full schema. Databases from before versioning got their columns
    added one by one as features were built; add any that are missing."""
    conn.executescript(SCHEMA)
    for table, column, definition in [
        ("expenses", "kind", "TEXT NOT NULL DEFAULT 'expense'"),
        ("expenses", "paid_date", "TEXT"),
        ("balance_checks", "account", "TEXT NOT NULL DEFAULT 'bank'"),
        ("budgets", "rollover", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        if column not in _columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


# MIGRATIONS[n] upgrades the database from version n to n + 1.
MIGRATIONS = [_v1_baseline]


def migrate():
    with connect() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for number, migration in enumerate(MIGRATIONS[version:], start=version + 1):
            migration(conn)
            conn.execute(f"PRAGMA user_version = {number}")


def daily_backup():
    """Copy the database to backups/ once a day, keeping the last KEEP_BACKUPS days."""
    if not DB_PATH.exists():
        return
    BACKUP_DIR.mkdir(exist_ok=True)
    target = BACKUP_DIR / f"budget-{date.today().isoformat()}.db"
    if target.exists():
        return
    with connect() as source, sqlite3.connect(target) as copy:
        source.backup(copy)  # consistent even while the app is in use
    for old in sorted(BACKUP_DIR.glob("budget-*.db"))[:-KEEP_BACKUPS]:
        old.unlink()
