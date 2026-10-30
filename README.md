# Budget

A personal budget app that runs on your own computer. Track spending and income against
monthly budgets, check your bank and savings balances, and see how your savings will
develop over the coming year.

## Installing it

Open `Budget.dmg` and drag Budget to Applications. Then start it like any other app. It
opens in its own window; closing the window quits it. Nothing else needs to be installed.

Budget is not signed with an Apple Developer account yet. On another Mac, the first start
is blocked: open System Settings > Privacy & Security and choose "Open Anyway". The
current build runs on Apple Silicon Macs only.

## Your data

- Everything stays on your Mac, in `~/Library/Application Support/nl.hendrikdemir.budget`
  (`budget.db`).
- A copy is made automatically in its `backups` folder once a day (the last 14 days are
  kept). To restore one, quit Budget and copy it over `budget.db`.

## What it does

- **Overview** per month: what's spent against your budgets, spending outside any budget,
  whether your bank balance covers next month's budget ("Ready for November?"), and all
  transactions with search and filters.
- **Budgets** per category, optionally split into items. Budgets can change from a month
  onward without affecting earlier months; unspent budget can carry over to next month.
- **Transactions**: expenses, income and transfers to/from savings. An expense can be
  split over several budgets; income can add to a budget.
- **Bank and savings balances**: set a starting point, check against your bank, and see
  the development per month.
- **Outlook**: a 12-month projection of your savings from expected income, budgets and
  planned expenses, and how much you can freely spend while keeping one month's budget
  as a buffer.

## For developers

Run from source, in the browser, with separate data in this folder (`budget.db`, `backups/`):

```bash
python3 server.py
```

Then open http://localhost:8000. To build `dist/Budget.app` and `dist/Budget.dmg`:

```bash
packaging/build.sh
```

- `desktop.py` — the Mac app: starts the server and opens the window.
- `server.py` — starts the server for development.
- `packaging/` — build script, app recipe and icon.
- `app/` — the server side (Python standard library only):
  `db.py` (schema, migrations, backups), `money.py` (validation), `budgets.py` (budgets
  and month totals), `accounts.py` (balances), `outlook.py` (next month and projection),
  `api.py` (the HTTP API), `web.py` (the web server).
- `static/` — the page: `index.html`, `style.css` and `js/` (plain ES modules, no build step).
