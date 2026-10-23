# STATUS.md — cashflow-simple-ledger

Last updated: 2026-10-22

## What was built

A local-first bookkeeping CLI (`cashflow`) for a small LLC or indie author,
by Asdale Dynamics, LLC. Pure Python 3.10+ standard library; zero runtime
dependencies. No network code at all — no cloud, no accounts, no keys.

Features:

- `init` — create a new empty portable ledger (`ledger.csv`)
- `add DATE AMOUNT DESCRIPTION [-c CATEGORY] [-a ACCOUNT]` — record
  income/expense (positive = income, negative = expense)
- `import BANK.csv [--account NAME] [--rules RULES] [--invert] [--dry-run]`
  — import bank CSV exports (date, amount, description) with tolerant CSV
  handling (case-insensitive headers, BOM, `$`/commas/parentheses amounts)
  and **portable dedupe**: every entry is fingerprinted by
  (date, amount, description, account), so re-downloading the same bank
  export never double-counts
- `categorize [-r RULES] [--dry-run]` — rule-file auto-categorization
  (`match_type,match_value,category` rules: contains / exact / regex,
  first match wins)
- `summary [-m YYYY-MM] [-y YYYY]` — monthly/yearly income, expenses, net,
  by-category breakdown, and a by-month table for years
- `list [-m] [-y] [-c] [-u]` — filtered entry listing
- `tax-export YYYY [--exclude "Transfers" ...] [-o FILE]` — clean
  `date,description,category,amount,type` CSV for one tax year, with totals
  printed when writing to a file
- Ledger storage is atomic (temp file + rename), sorted, and has a stable
  header so every tool that reads CSV can read it

## Layout

```
cashflow/            package: cli.py, ledger.py, importer.py, rules.py,
                     summary.py, tax.py
tests/               pytest suite (110 tests)
sample-data/         bank-export.csv, credit-card.csv, rules.csv
pyproject.toml       packaging (`cashflow` console script)
README.md            full documentation with sample-data walkthrough
LICENSE              MIT, Copyright (c) 2026 Asdale Dynamics, LLC
```

## How to run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cashflow --help                      # or: python -m cashflow (no install needed)
```

Quickstart with the included sample data (see README for full output):

```bash
cashflow init
cashflow import sample-data/bank-export.csv --account checking -r sample-data/rules.csv
cashflow summary --month 2026-10
cashflow tax-export 2026 --exclude Transfers -o tax-2026.csv
```

## Verification results (2026-10-22, Python 3.13.5)

- `python -m pytest` — **110 passed** in ~0.4s
- `python -m compileall cashflow tests` — clean, no syntax warnings
- End-to-end demo run (fresh folder): init → add → import bank export
  (12 added, 1 internal duplicate skipped, 12 auto-categorized) → re-import
  (0 added, 13 duplicates skipped) → second-account import → categorize →
  list → monthly summary (income $249.94 / expenses $474.21) → yearly
  summary with by-month table → tax export with Transfers excluded
  (Income $249.94 / Expenses $274.21 / Net -$24.27)
- Error paths verified: duplicate `add` exits 1 with a clear message, bad
  dates/amounts/months exit 1 and never leave a half-written ledger, bank
  rows are validated fully before anything is saved (a bad row aborts the
  whole import)
- `pip install -e .` in a clean virtualenv builds and installs the
  `cashflow` console script; `python -m cashflow` works from the repo
  without any install (verified via subprocess test from a scratch cwd)

## Known gaps

- Expense report formats beyond CSV (OFX/QIF/xlsx) are not supported
- Categories are free-form strings; there is no fixed category list or
  renaming/migration command
- No editing command — change categories/descriptions by editing the CSV
  directly (keep the `id` column if you want dedupe to keep working)
- Rules match on description text only (no column-based rules yet)
- Tax export reports totals but does not compute anything like
  quarterly estimates, mileage, or home-office deductions
- Multi-currency is out of scope; all entries are taken as one currency
- The yearly summary table prints only months that have entries
