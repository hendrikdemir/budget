"""Budget — a tiny local spending tracker. See README.md and CLAUDE.md for an overview.

Modules:
- db:       database connection, schema, migrations and daily backups
- money:    validation helpers and month arithmetic (all money is in whole cents)
- budgets:  budget history, carry-over, and a month's budget lines and totals
- accounts: bank/savings balances and balance checks
- outlook:  "ready for next month?" and the savings projection
- api:      HTTP API handlers and routes
"""

VERSION = "1.0.0"  # shown in Settings and used for the Mac app
