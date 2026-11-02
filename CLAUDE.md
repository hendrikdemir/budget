# CLAUDE.md

Guidance for working on this repository.

## What this is

A single-user, local budget app, delivered as a Mac app (`Budget.app`). `desktop.py` starts
the server on 127.0.0.1 and shows the page in a window (pywebview, so Safari's WebKit engine).
Its data is in `~/Library/Application Support/nl.hendrikdemir.budget`.

`python3 server.py` runs the same app in a browser on port 8000, with separate data in this
folder (`budget.db`, `backups/`). With `--demo` it uses a made-up household in `.demo-data/`
(`app/demo.py`), which is what the preview in `.claude/launch.json` shows. The app itself needs only the Python standard library;
pywebview and PyInstaller are used for the Mac app. There is no web build step.

## Layout

- `desktop.py`: the Mac app. `server.py`: development entry point.
- `packaging/`: `build.sh` builds `dist/Budget.app` and `dist/Budget.dmg`. The version is `VERSION` in
  `app/__init__.py`. It stays 1.0.0 until the first release; only raise it for a new release.
- `app/web.py`: HTTP server. Routes `/api/<resource>[/<id>]` to `app/api.py` `ROUTES`,
  everything else to `static/`. Sends `Cache-Control: no-cache`.
  It only answers the app's own page (checks Host, Origin and Content-Type), so websites open
  in a browser can't use it; keep that when adding routes or request types.
- `app/db.py`: schema and **migrations**. The schema version is SQLite's `user_version`.
  To change the schema, append a function to `MIGRATIONS` (never edit an old one).
- `app/budgets.py`: budget history, carry-over, transactions, and `month_data()`, which
  computes a month's budget lines, totals and leftover.
- `app/accounts.py`: expected balances (starting point + transactions by paid date).
- `app/outlook.py`: `month_outlook()` ("ready for next month?") and `projection()`.
- `app/bank_import.py`: reading bank exports (CSV) for review. One reader per bank in
  `READERS` (ING for now); `preview()` adds payee, budget and duplicate suggestions.
- `app/backup.py`: export and import. Bump nothing here for schema changes: a backup's version is
  its `user_version`, and imports run the normal migrations.
- `app/api.py`: request handlers; validation helpers are in `app/money.py`.
- `static/js/`: ES modules. `main.js` starts the page; `overview.js`, `transaction.js`,
  `budget-editor.js`, `accounts.js`, `outlook.js`, `settings.js`, `bank-import.js` each own a part of the UI;
  `format.js`, `ui.js`, `controls.js`, `chart.js`, `state.js` are shared helpers.

## Conventions

- **Money is whole cents everywhere**: database, API (requests and responses) and JS.
  Convert only for display (`money()`) and input (`parseAmount()` -> cents,
  `inputAmount()` for input fields). Never do money math in floats.
- **Calculations belong on the server.** The browser renders what `/api/month`,
  `/api/projection` etc. return; it may only do small UI arithmetic (e.g. the
  transaction dialog's preview).
- Budget lines are keyed `i<id>` (item) or `c<id>` (category without items).
  Transactions are stored in the `expenses` table with `kind` expense/income/save/withdraw.
- History-based data (budgets, plan amounts) changes "from a month onward"; earlier
  months must never change.
- UI text is English, including month and day names (`DATE_LOCALE` in `format.js`); numbers
  and amounts follow the browser's locale. Errors shown to the user are friendly and say what to do.
- Styles: CSS custom properties in `static/style.css`, light and dark themes,
  one fixed palette: warm paper and ink with petrol, a petrol and peach glow behind frosted
  cards, and red only for being over budget. Match existing components (cards, `.bl-row`, `.mgr-row`, dialogs).

## Keeping the installed app current

The owner uses the app from `/Applications`, which doesn't change by itself. `packaging/install.sh`
builds, replaces the installed copy and reopens it if it was open; data isn't affected. Run it only
when the owner asks; until then, remind them at the end of each change that the installed app is behind.

## Keeping the preview current

The preview's server doesn't reload code. After changing anything in `app/` or `server.py`, restart
it before reporting the work; otherwise the page can call routes the running server doesn't know.

## Keeping the README current

Update `README.md` and the screenshots only when the owner asks; until then, remind them at the end of
each change what's out of date. When updating:

- Update the text when a feature, label, install step, requirement or file path it mentions changes.
- If a change is visible in a screenshot, regenerate them with `packaging/make_screenshots.py`
  (made-up data only, never real data) and look at the results. If it adds a screen or flow worth
  showing, add it to the script and the README.
- If the README needs no change, say so when reporting the work.

## Checking changes

The Mac app uses WebKit, which behaves differently from Chrome: test real mouse clicks there (not
`element.click()`). For example, WebKit cancels a click on a button whose text changed during the
mouse press. `packaging/make_screenshots.py` shows how to drive WebKit with Playwright.

Run the tests with `python3 -m unittest` (standard library only, about 2 seconds). They live in
`tests/` and cover budgets, the outlook, bank imports and the server's protection, with made-up
data and a fixed "today" (`tests/base.py`). Add a test when changing a calculation or adding a
bank reader. The tests don't cover the page itself: after a change, also run the app and check the affected screens
in the browser (light and dark, desktop and mobile width). Test the built app too when
changing `desktop.py` or packaging, with `BUDGET_DATA_DIR` pointing to a copy of the data. For changes to calculations,
compare the numbers shown before and after the change on real data.
