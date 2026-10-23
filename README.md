# Cashflow — a local-first bookkeeping CLI

A tiny, friendly command-line bookkeeper for a sole-proprietor LLC, an
indie author, or anyone who just wants their money tracked **locally** in
plain CSV files. No accounts to create, no cloud to trust, no API keys —
your ledger is a portable CSV you can open in any spreadsheet app, sync,
back up, or keep in git.

Built and maintained by **Asdale Dynamics, LLC** (Dylan Asdale's LLC), in
the same plain-English, step-by-step spirit as his books — never condescending.

## What it does

- **Record income/expenses by category** — `cashflow add 2026-10-05 -6.99 "Pens"`
- **Import bank CSV exports** (date, amount, description) with **dedupe-aware**
  imports: re-download the same export twice and nothing gets double-counted
- **Rule-file auto-categorization** — one small CSV of match rules, applied on
  import or later with `cashflow categorize`
- **Portable ledger** — a single `ledger.csv` with stable ids, sorted output,
  and atomic writes
- **Monthly and yearly summaries** — income, expenses, net, by category
- **Simple tax-season export** — clean `date,description,category,amount,type`
  CSV for one tax year, excluding transfers

## Conventions (plain English)

- **Positive amounts are income; negative amounts are expenses.**
- Dates are `YYYY-MM-DD`.
- Categories are a small set you invent for yourself (Office Supplies,
  Software, Book Royalties...). Anything not categorized yet shows as
  `Uncategorized`.
- **Transfers to your own accounts** (e.g. moving money to savings) are
  recorded like anything else, but tagged with a category such as
  `Transfers` so one flag leaves them out of the tax export.
- Every entry has a deterministic **id** (a fingerprint of date, amount,
  description, and account). Same transaction → same id, in every copy of
  your ledger. That is what makes dedupe portable.

## Install

Python 3.10+ only; there are zero runtime dependencies.

```bash
# Option A: install the `cashflow` command into a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
cashflow --version

# Option B: no install at all, run from the repo folder
python -m cashflow --version
```

## Quickstart (with the included sample data)

Run these from the repository folder to see everything work end to end:

```bash
cashflow init                                            # creates ledger.csv
cashflow add 2026-10-05 -6.99 "Pens and sticky notes"     # a manual expense
cashflow add 2026-10-20 54.75 "Direct ebook sale" -c "Book Sales"

# import a bank export, auto-categorize with the sample rules file
cashflow import sample-data/bank-export.csv --account checking -r sample-data/rules.csv

# import it again — dedupe makes this a safe no-op
cashflow import sample-data/bank-export.csv --account checking

# a second account (credit card) joins the same ledger
cashflow import sample-data/credit-card.csv --account card -r sample-data/rules.csv

# fill in anything still Uncategorized using rules.csv
cashflow categorize

# look at what you have
cashflow list --month 2026-10
cashflow list --uncategorized

# money in vs. money out
cashflow summary --month 2026-10
cashflow summary --year 2026

# tax season: clean CSV for one year, transfers excluded, totals printed
cashflow tax-export 2026 --exclude Transfers -o tax-2026.csv
```

Sample output, using the included sample data:

```
Cashflow summary for 2026-10 (ledger.csv)
Entries:   15
Income:    $249.94
Expenses:  $474.21
Net:       -$224.27

Income by category:
  Book Royalties                $105.20
  Book Sales                    $144.74

Expenses by category:
  Uncategorized                  $14.47
  Equipment                      $18.00
  Marketing                      $14.99
  ...snip...
```

## Files

One folder per business/bookkeeping life works well:

- `ledger.csv` — your ledger (default; `-f/--file` points anywhere else)
- `rules.csv` — your auto-categorization rules
- `sample-data/` — example bank export, credit-card export, and rules file
- `tax-YYYY.csv` — whatever you name your tax-season exports

`ledger.csv` looks like this:

```csv
id,date,amount,description,category,account,source
f68e34cc9c2b6e20,2026-10-03,-24.97,STAPLES 00121 OFFICE SUPPLIES,Office Supplies,checking,bank-export.csv
```

## The rules file

CSV with three columns applied top to bottom, first match wins:

```csv
match_type,match_value,category
contains,KDP,Book Royalties
contains,STAPLES,Office Supplies
regex,^GODADDY\.COM,Website
exact,ONLINE TRANSFER TO SAVINGS 4417,Transfers
```

- `contains` — case-insensitive substring test (the workhorse)
- `exact` — the whole description matches (case-insensitive)
- `regex` — regular expression, for the picky cases

## Command reference

| Command | What it does |
| --- | --- |
| `cashflow init` | Create a new, empty ledger file |
| `cashflow add DATE AMOUNT DESCRIPTION [-c CATEGORY] [-a ACCOUNT]` | Record one entry |
| `cashflow import BANK.csv [-a ACCOUNT] [-r RULES] [-c CATEGORY] [--invert] [-n]` | Import a bank CSV, dedupe-aware |
| `cashflow categorize [-r RULES] [-n]` | Auto-categorize everything uncategorized |
| `cashflow summary [-m YYYY-MM] [-y YYYY]` | Totals by category (with by-month table for years) |
| `cashflow list [-m] [-y] [-c] [-u]` | List entries with filters |
| `cashflow tax-export YEAR [-x CATS] [-o FILE]` | One-year clean CSV; prints totals |

Global: `-f/--file LEDGER` chooses the ledger file (before or after the
subcommand). Defaults to `ledger.csv` in the current directory.

Handy flags:

- `import --invert` — some banks export debits as positive numbers; this flips signs
- `import --dry-run` / `categorize --dry-run` — preview without writing
- `add --category/--account` — fully specify an entry up front
- `tax-export --exclude "Transfers,Reimbursements"` — keep your own money moves out of the CPA file

## Developers

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
python -m pytest            # 110 tests, all stdlib + pytest
```

Project layout:

```
cashflow/           the package
  cli.py            argparse interface
  ledger.py         portable CSV store + dedupe ids
  importer.py       bank CSV import
  rules.py          rule-file auto-categorization
  summary.py        monthly/yearly summaries
  tax.py            tax-season export
tests/              pytest suite
sample-data/        sample bank/credit-card exports and rules file
```

## Privacy and data safety

Everything is a local CSV. Nothing phones home; there is no network code at
all. Keep your ledger in a private folder or private git repo — with
descriptions like "PANERA BREAD 4471" it is not sensitive, but it is yours.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Asdale Dynamics, LLC.

Part of the Asdale Dynamics, LLC family of plain-English, local-first tools.
More at [dylanasdale.github.io](https://dylanasdale.github.io).
