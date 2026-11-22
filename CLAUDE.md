# CLAUDE.md

Guidance for working on this repository.

## What this is

A single-user, local budget app for Mac and Windows: `Budget.app` (in `Budget.dmg`) and an installer,
`Budget-setup.exe`. `desktop.py` starts the server on 127.0.0.1 and shows the page in a window
(pywebview: Safari's WebKit on the Mac, Edge's WebView2 on Windows). Its data is in
`~/Library/Application Support/nl.hendrikdemir.budget` on a Mac and `%APPDATA%\Budget` on Windows.

`python3 server.py` runs the same app in a browser on port 8000, with separate data in this
folder (`budget.db`, `backups/`). With `--demo` it uses a made-up household in `.demo-data/`
(`app/demo.py`), which is what the preview in `.claude/launch.json` shows. With `--empty` it starts
without any data, as a new user sees it (the `budget-empty` preview; emptied at every start). The app itself needs only the Python standard library;
pywebview and PyInstaller are used for the desktop app. There is no web build step.

## Layout

- `desktop.py`: the desktop app (Mac and Windows). `server.py`: development entry point.
- `packaging/`: `build.sh` builds `dist/Budget.app` and `dist/Budget.dmg` (Mac). `build-windows.ps1`
  builds the Windows app and its Inno Setup installer `dist\Budget-setup.exe` (`Budget.iss`); GitHub
  builds and tests it on Windows for every push to main and every release tag
  (`.github/workflows/windows.yml`). The version is `VERSION` in `app/__init__.py`. Don't change it by
  hand: `release.py` sets it when releasing (it suggests patch/minor/major from what changed, and asks
  which systems the release is for), builds, tags `v<VERSION>`, pushes and publishes the GitHub release.
- `docs/`: the website (GitHub Pages) and the screenshots. Its download buttons look up the newest
  release with each system's file, like the app's update check.
- `app/web.py`: HTTP server. Routes `/api/<resource>[/<id>]` to `app/api.py` `ROUTES`,
  everything else to `static/`. Sends `Cache-Control: no-cache`.
  It only answers the app's own page (checks Host, Origin and Content-Type), so websites open
  in a browser can't use it; keep that when adding routes or request types.
- `app/db.py`: schema and **migrations**. The schema version is SQLite's `user_version`.
  To change the schema, append a function to `MIGRATIONS` (never edit an old one).
  Use `db.session()` for a connection (it commits and closes). A connection remembers results
  from `conn.cached()` (budget lines with their carry-over, `month_data()`) until it changes data
  itself; those results are shared, so copy before adding to them.
- `app/budgets.py`: budget history, carry-over, transactions, and `month_data()`, which
  computes a month's budget lines, totals and leftover.
- `app/accounts.py`: expected balances (starting point + transactions by paid date) and `year_history()`
  for the History page; `budgets.budget_history()` adds each budget per month.
- `app/outlook.py`: `month_outlook()` ("ready for next month?") and `projection()`. Plans
  repeat once, monthly or every `every_months` months (`falls_in()`).
- `app/bank_import.py`: reading bank exports (CSV) for review. One reader per bank in
  `READERS` (ING, and `BudgetReader` for Budget's own exports, with budgets by name and
  splits); `preview()` adds payee, budget and duplicate suggestions.
- `app/export.py`: transactions as CSV (a row per split part), for the Export menu and selection.
- `app/backup.py`: creating and restoring backups (a file, or the automatic daily ones from
  `db.daily_backup()`), and deleting all data. Bump nothing here for schema changes: a backup's version is
  its `user_version`, and imports run the normal migrations.
- `app/updates.py`: asks GitHub (at most once a day) whether a newer release exists for this system
  (one with its Budget.dmg or Budget-setup.exe, so a release can be for the Mac or Windows only); the page
  only tells the user and explains how to install it. `BUDGET_RELEASES_URL` (e.g.
  `packaging/test-release.json`, used by the `budget-update` preview) fakes a release for testing.
- `app/api.py`: request handlers; validation helpers are in `app/money.py`. `app/i18n.py`: the
  server's side of the language files.
- `static/js/`: ES modules. `main.js` starts the page; `overview.js`, `transaction.js`,
  `budget-editor.js`, `accounts.js`, `history.js`, `outlook.js`, `settings.js`, `bank-import.js`, `updates.js`, `guide.js` (getting started and
  feature offers) each own a part of the UI; `format.js`, `ui.js`, `controls.js`, `chart.js`, `state.js`, `help.js` are shared
  helpers, and `i18n.js` loads the language (it runs first: other modules can translate at load time).

## Conventions

- **Money is whole cents everywhere**: database, API (requests and responses) and JS.
  Convert only for display (`money()`) and input (`parseAmount()` -> cents,
  `inputAmount()` for input fields). Never do money math in floats.
- **Numbers are written the user's way**: 1.234,56 or 1,234.56, as this computer does or as chosen in
  Settings (`number_format`). Example numbers in messages and placeholders follow it too: use
  `example("12.50")` in the page, and write `{12.50}` in a server error (the page converts it).
- **Calculations belong on the server.** The browser renders what `/api/month`,
  `/api/projection` etc. return; it may only do small UI arithmetic (e.g. the
  transaction dialog's preview).
- Budget lines are keyed `i<id>` (item) or `c<id>` (category without items). A category that
  gets items later keeps its own budget in the months before (`single` in `categories_for()`).
- Wrap handlers that save something in `once()` (`ui.js`), so a double click can't save twice.
  Transactions are stored in the `expenses` table with `kind` expense/income/save/withdraw.
- History-based data (budgets, plan amounts) changes "from a month onward"; earlier
  months must never change.
- **Every text is in a language file**, never in code: `static/lang/en.json` (the source) and a file
  per translation (`nl.json`), under named keys grouped by part of the app, in i18next's JSON format
  (`{{name}}` values, `_one`/`_other` plurals). The page uses `t("budgets.editBudgets", { … })` and
  `data-i18n…` attributes in `index.html`; the server raises `ApiError("errors.…", **params)` and
  sends it in the page's language (`app/i18n.py`). Add or change English in `en.json` and the same
  key in every other language; `tests/test_i18n.py` fails on missing, unused or mismatched keys.
  Month and day names follow the language (`DATE_LOCALE` in `format.js`). Errors shown to the user
  are friendly and say what to do.
- **Simple and Extended**: Settings › Mode is Simple (`mode` simple, the default for new data) or
  Extended (`mode` full, every feature). Features beyond the basics get class `full-only` (or check `isSimple()`);
  `offers()` in `app/api.py` suggests them once they're useful. Simple mode starts with
  budgets and spending only; the bank and savings balances are offered later, and their rows
  show once they're set up. Plain-language explanations are
  "?" buttons from `help.js`.
- Styles: CSS custom properties in `static/style.css`, light and dark themes,
  one fixed palette of greens and slate blues (#c9e4ca, #87bba2, #55828b, #3b6064, #364958),
  a soft glow behind frosted cards, and red only for being over budget. One font everywhere: Geist,
  shipped in `static/fonts/` (SIL Open Font License), so the app looks the same on every system
  and never loads anything from the internet. Match existing components (cards, `.bl-row`, `.mgr-row`, dialogs).

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
The Windows app uses Edge's WebView2 (Chromium) instead. There's no Windows computer here: the
Windows build on GitHub runs the tests and installs and uninstalls the installer; the owner tries
builds in a Windows VM. Paths, file names and text files must work on both (read and write as UTF-8).

Run the tests with `python3 -m unittest` (standard library only, about 2 seconds). They live in
`tests/` and cover budgets, the outlook, bank imports, the server's protection and the language files, with made-up
data and a fixed "today" (`tests/base.py`). Add a test when changing a calculation or adding a
bank reader. The tests don't cover the page itself: after a change, also run the app and check the affected screens
in the browser (light and dark, desktop and mobile width). Test the built app too when
changing `desktop.py` or packaging, with `BUDGET_DATA_DIR` pointing to a copy of the data. For changes to calculations,
compare the numbers shown before and after the change on real data.
