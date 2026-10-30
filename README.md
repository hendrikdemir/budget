<div align="center">

<img src="packaging/icon.png" width="120" alt="Budget app icon">

# Budget

**A calm, private budget app for your Mac.**

Plan every euro, see what's left at a glance, and know whether your savings will hold up in the year ahead.

No account. No subscription. No cloud. Your data stays on your Mac.

</div>

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/overview-dark.png">
  <img src="docs/screenshots/overview-light.png" alt="The Budget overview: spending this month, whether you're ready for next month, account balances and budgets">
</picture>

<p align="center"><sub>All screenshots show the real app with made-up data.</sub></p>

## What it does

### See your month at a glance

Your spending, what's left in each budget, and anything spent outside your budgets, all on one page. Budgets go red only when you've overspent, so the page stays calm until something needs your attention.

**Ready for next month?** Budget compares your bank balance with what next month needs and tells you exactly how much is short or spare, with one click to move the difference to or from your savings.

### Budgets that fit real life

<img src="docs/screenshots/budgets.png" alt="The budget list with categories, items and remaining amounts">

- **Categories and items**, such as Home › Rent, Energy and Internet, or a single budget like Fun money.
- **Budgets that change over time.** Raise the rent from next month and earlier months stay exactly as they were.
- **Carry leftovers over** to next month, by default or case by case, and see how much came along.

### Add a transaction and see the effect first

<table>
<tr>
<td width="50%"><img src="docs/screenshots/transaction.png" alt="Adding an expense split across two budgets, with a preview that one goes over"></td>
<td>

- **Split** one purchase across several budgets.
- **See the effect before you save:** a preview shows what's left in each budget, in red if it would go over.
- **Income** can top up a budget. Sold something online? Add it to your Fun money.
- **Bills paid in advance** can count for one month and leave your bank in another.
- **Quick entry:** known payees suggest the budget you used last time, and pressing <kbd>N</kbd> or <kbd>I</kbd> opens a new expense or income.

</td>
</tr>
</table>

### Find anything

<img src="docs/screenshots/transactions.png" alt="Searching the transaction list">

Transactions are grouped per day. Search by payee, note, budget or amount, filter by type, and search across all months. Click a budget to see only its transactions, or select several to delete them at once.

### Keep your balances honest

<table>
<tr>
<td>

Set a starting balance for your bank account and savings, and Budget keeps track from there. Enter what your bank shows at any time: it tells you whether everything matches, or how much is off.

Follow the development of your savings through the year, month by month.

</td>
<td width="50%"><img src="docs/screenshots/savings.png" alt="The savings account with its development chart"></td>
</tr>
</table>

### Look ahead with the Outlook

<img src="docs/screenshots/outlook.png" alt="The Outlook: projected savings for the next twelve months">

Add your expected income and planned costs, like a holiday or a new laptop, and Budget projects your savings for the next 12 months. It keeps a safety buffer in your savings and shows how much you can **freely spend** without dipping below it in any month ahead. You choose the buffer: a number of months of budget, or a fixed amount.

<img src="docs/screenshots/buffer.png" width="420" alt="Choosing the savings buffer: months of budget or a fixed amount">

### Make it yours

<img src="docs/screenshots/appearance.png" width="420" alt="Appearance settings with accent colors, theme and currency">

Choose an accent color, follow your Mac's light or dark mode, and pick your currency.

## Installing

1. Download `Budget.dmg` from the [Releases](../../releases) page.
2. Open it and drag **Budget** to **Applications**.
3. Open Budget. Nothing else needs to be installed.

> [!NOTE]
> Budget isn't signed with an Apple Developer account yet, so macOS blocks the first start. Open **System Settings → Privacy & Security** and choose **Open Anyway**. You only need to do this once.

Budget currently runs on Macs with Apple Silicon.

## Your data

Everything stays on your Mac, in `~/Library/Application Support/nl.hendrikdemir.budget`. Budget makes a backup automatically once a day and keeps the last 14 days in the `backups` folder there. To restore one, quit Budget and copy it over `budget.db`.

## For developers

Budget is a small Python and JavaScript app. It uses SQLite and only the Python standard library, with no web build step.

Run it from source in your browser, with separate data in this folder:

```bash
python3 server.py
```

Then open http://localhost:8000.

Build `dist/Budget.app` and `dist/Budget.dmg`:

```bash
packaging/build.sh
```

Build and replace the copy in Applications (your data isn't affected):

```bash
packaging/install.sh
```

Update the screenshots, using made-up data:

```bash
.venv-build/bin/python packaging/make_screenshots.py
```

| Path | Contents |
| --- | --- |
| `desktop.py` | The Mac app: starts the server and opens the window |
| `server.py` | Starts the server for development |
| `app/` | Server side: database, budgets, balances, outlook and API |
| `static/` | The page: HTML, CSS and JavaScript modules |
| `packaging/` | App build, icon and screenshots |
