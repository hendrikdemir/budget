"""Database connection, schema, migrations and daily backups.

To change the schema, add a function to MIGRATIONS; it runs once on databases that are older,
in order. SQLite's `user_version` is the version an older Budget must know to open the data: only
migrations that older versions can't cope with raise it. Mark the others @readable_by_older
(see below). How many migrations ran is the `migrations` setting.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from . import VERSION

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
    end_month TEXT,                -- YYYY-MM, inclusive; NULL = ongoing
    every_months INTEGER NOT NULL DEFAULT 1  -- 1 = every month, 2 = every other month, ...
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
    if os.name != "nt":
        folder.chmod(0o700)  # financial data: for this user only (Windows keeps %APPDATA% per user)
    DB_PATH = folder / "budget.db"
    BACKUP_DIR = folder / "backups"


class Connection(sqlite3.Connection):
    """A connection that can remember results worked out from its data (see `cached`)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache = {}

    def cached(self, key, compute):
        """`compute()`, worked out again only once this connection changed the data since.
        Only for results that depend on the data alone, and that callers don't change."""
        changes = self.total_changes
        if key not in self.cache or self.cache[key][0] != changes:
            self.cache[key] = (changes, compute())
        return self.cache[key][1]


def connect():
    """A connection to the data. Close it when done; `session()` does that for you."""
    conn = sqlite3.connect(DB_PATH, factory=Connection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session():
    """A connection whose changes are saved together (or not at all, after an error), and
    that is closed afterwards."""
    conn = connect()
    try:
        with conn:  # commits, or rolls back after an error
            yield conn
    finally:
        conn.close()


def _columns(conn, table):
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


def readable_by_older(migration):
    """Marks a migration that older versions of Budget can live with: they still read and write
    the data correctly (e.g. a new setting or table they ignore, an index). Then going back to an
    older version keeps working. Leave it off when older versions would misread the data or
    write it wrong, e.g. a new column whose value they'd ignore or a changed meaning."""
    migration.readable_by_older = True
    return migration


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


def _v2_plan_interval(conn):
    """Version 2: plans can repeat every few months (every_months), not only every month."""
    if "every_months" not in _columns(conn, "plans"):
        conn.execute("ALTER TABLE plans ADD COLUMN every_months INTEGER NOT NULL DEFAULT 1")


@readable_by_older
def _v3_mode(conn):
    """Version 3: Budget can show only the basics (setting mode "simple", the default for new
    data). Data from before keeps every feature it had: mode "full"."""
    if conn.execute("SELECT 1 FROM expenses UNION ALL SELECT 1 FROM budgets UNION ALL SELECT 1 FROM plans LIMIT 1").fetchone():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('mode', 'full')")


# MIGRATIONS[n] upgrades the database from version n to n + 1.
MIGRATIONS = [_v1_baseline, _v2_plan_interval, _v3_mode]


class TooNewError(Exception):
    """The data was last used by a newer Budget than this one (for example after reinstalling
    an older version). This version doesn't know its newer structure, so it mustn't touch it.
    `used_with` is the version that last opened the data (None if it predates recording that),
    `language` and `theme` as chosen in Settings."""

    def __init__(self, used_with=None, language="system", theme="system"):
        super().__init__("Your data was last used with a newer version of Budget"
                         + (f" ({used_with})" if used_with else "") + f" than this one ({VERSION}). "
                         "Install the latest version from https://github.com/hendrikdemir/budget/releases "
                         "to keep using it. Your data hasn't changed.")
        self.used_with, self.language, self.theme = used_with, language, theme


def _setting(conn, key):
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def needed_by_older():
    """The user_version for this version's data: the last migration older versions can't live with.
    (Budget 0.11 and earlier raised it for every migration; this lowers it back.)"""
    return max((n for n, m in enumerate(MIGRATIONS, start=1) if not getattr(m, "readable_by_older", False)), default=0)


def _done(conn, needed):
    """How many migrations ran: the `migrations` setting, else (data from Budget 0.11 or earlier) user_version."""
    value = _setting(conn, "migrations")
    return max(int(value), needed) if value and value.isdigit() else needed


def migrate():
    with session() as conn:
        needed = conn.execute("PRAGMA user_version").fetchone()[0]
        if needed > len(MIGRATIONS):
            raise TooNewError(_setting(conn, "app_version"), _setting(conn, "language") or "system",
                              _setting(conn, "theme") or "system")
        done = _done(conn, needed)
        for migration in MIGRATIONS[done:]:
            migration(conn)
        # Newer data with only changes this version can live with is used as it is.
        done = max(done, len(MIGRATIONS))  # more, if a newer Budget ran ones this version doesn't know
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('migrations', ?)", (str(done),))
        conn.execute(f"PRAGMA user_version = {needed_by_older()}")
        # Remembered so an older Budget opening this data later can say which version it needs.
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('app_version', ?)", (VERSION,))


def daily_backup():
    """Copy the database to backups/ once a day, keeping the last KEEP_BACKUPS days."""
    if not DB_PATH.exists():
        return
    BACKUP_DIR.mkdir(exist_ok=True)
    target = BACKUP_DIR / f"budget-{date.today().isoformat()}.db"
    if target.exists():
        return
    source, copy = connect(), sqlite3.connect(target)
    try:
        source.backup(copy)  # consistent even while the app is in use
    finally:
        copy.close()
        source.close()
    for old in sorted(BACKUP_DIR.glob("budget-*.db"))[:-KEEP_BACKUPS]:
        old.unlink()
