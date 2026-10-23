"""Command-line interface for cashflow."""
from __future__ import annotations

import argparse
import sys
from datetime import date as _date
from pathlib import Path

from . import __version__
from .importer import import_bank_csv
from .ledger import (
    DEFAULT_ACCOUNT,
    DEFAULT_FILE,
    Entry,
    LedgerError,
    MANUAL_SOURCE,
    append_entry,
    cents,
    load_ledger,
    parse_amount,
    save_ledger,
    validate_date,
)
from .rules import RulesError, apply_rules, load_rules
from .summary import filter_entries, money, monthly_breakdown, render_summary, summarize
from .tax import tax_csv_text, tax_lines, tax_totals, write_tax_csv


class CliError(Exception):
    """A user-facing CLI error (bad arguments, missing files, ...)."""


def _add_file_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-f",
        "--file",
        dest="file_sub",
        default=None,
        metavar="LEDGER",
        help="Ledger CSV file (default: ledger.csv in the current directory).",
    )


def _ledger_path(args: argparse.Namespace) -> str:
    return getattr(args, "file_sub", None) or getattr(args, "file_top", None) or DEFAULT_FILE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cashflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Local-first bookkeeping: record categorized income/expenses, import bank"
            " CSV exports with dedupe, auto-categorize from a rules file, get monthly"
            " summaries and tax-season exports. Everything stays in plain CSV files."
        ),
        epilog="Examples:\n  cashflow add 2026-10-05 -6.99 \"Pens\"\n  cashflow import bank.csv --rules rules.csv",
    )
    parser.add_argument(
        "-f", "--file", dest="file_top", default=DEFAULT_FILE, metavar="LEDGER",
        help="Ledger CSV file used by all commands (default: ledger.csv).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="Create a new, empty ledger file.")
    _add_file_option(p_init)
    p_init.set_defaults(func=cmd_init)

    p_add = subparsers.add_parser("add", help="Record one income/expense by hand.")
    _add_file_option(p_add)
    p_add.add_argument("date", help="Date, YYYY-MM-DD.")
    p_add.add_argument("amount", help="Signed amount: positive = income, negative = expense.")
    p_add.add_argument("description", help="What it was for (quoted text).")
    p_add.add_argument("-c", "--category", default="", help="Category, e.g. Office Supplies. Optional.")
    p_add.add_argument("-a", "--account", default=DEFAULT_ACCOUNT, help="Account name (default: cash).")
    p_add.set_defaults(func=cmd_add)

    p_import = subparsers.add_parser("import", help="Import a bank CSV export (dedupe-aware).")
    _add_file_option(p_import)
    p_import.add_argument("bank", help="Bank CSV file with date, amount, description columns.")
    p_import.add_argument("-a", "--account", default=None, help="Account name (default: bank file's name).")
    p_import.add_argument("-r", "--rules", default=None, help="Rules CSV to auto-categorize imported rows.")
    p_import.add_argument("-c", "--category", default="", help="Give every imported row this category (before rules).")
    p_import.add_argument("--invert", action="store_true", help="Flip amount signs (for banks that export debits as positive).")
    p_import.add_argument("-n", "--dry-run", action="store_true", help="Preview what would be added; write nothing.")
    p_import.set_defaults(func=cmd_import)

    p_categorize = subparsers.add_parser("categorize", help="Auto-categorize uncategorized entries using a rules file.")
    _add_file_option(p_categorize)
    p_categorize.add_argument("-r", "--rules", default="rules.csv", help="Rules CSV (default: rules.csv).")
    p_categorize.add_argument("-n", "--dry-run", action="store_true", help="Show how many entries would be categorized; write nothing.")
    p_categorize.set_defaults(func=cmd_categorize)

    p_summary = subparsers.add_parser("summary", help="Income/expense totals by category.")
    _add_file_option(p_summary)
    p_summary.add_argument("-m", "--month", default=None, help="Limit to one month, e.g. 2026-10.")
    p_summary.add_argument("-y", "--year", default=None, help="Limit to one year, e.g. 2026 (adds a by-month table).")
    p_summary.set_defaults(func=cmd_summary)

    p_list = subparsers.add_parser("list", help="List entries with simple filters.")
    _add_file_option(p_list)
    p_list.add_argument("-m", "--month", default=None, help="Only this month, e.g. 2026-10.")
    p_list.add_argument("-y", "--year", default=None, help="Only this year, e.g. 2026.")
    p_list.add_argument("-c", "--category", default=None, help="Only this category.")
    p_list.add_argument("-u", "--uncategorized", action="store_true", help="Only entries without a category.")
    p_list.set_defaults(func=cmd_list)

    p_tax = subparsers.add_parser("tax-export", help="Export one tax year to a clean CSV.")
    _add_file_option(p_tax)
    p_tax.add_argument("year", help="Tax year, e.g. 2026.")
    p_tax.add_argument("-x", "--exclude", default="", help="Comma-separated categories to skip (e.g. Transfers).")
    p_tax.add_argument("-o", "--output", default=None, help="Output CSV file. Without it, the CSV prints to stdout.")
    p_tax.set_defaults(func=cmd_tax_export)

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    path = _ledger_path(args)
    if Path(path).exists():
        raise CliError(f"{path} already exists. Pass -f PATH to use another file, or keep using it.")
    save_ledger(path, [])
    print(f"Created empty ledger file: {path}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    path = _ledger_path(args)
    date_text = validate_date(args.date)
    amount = parse_amount(args.amount)
    if amount == 0:
        raise CliError("Amount cannot be zero. Use a negative amount for expenses, positive for income.")
    description = args.description.strip()
    if not description:
        raise CliError("Description cannot be empty.")
    entry = Entry(
        date=date_text,
        amount=amount,
        description=description,
        category=(args.category or "").strip(),
        account=(args.account or DEFAULT_ACCOUNT).strip(),
        source=MANUAL_SOURCE,
    )
    try:
        append_entry(path, entry)
    except LedgerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Added: {entry.date} {money(entry.amount)} {entry.description!r} (account: {entry.account})")
    if not entry.category:
        print("Left uncategorized. Run 'cashflow categorize' to fill it in from rules.")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    path = _ledger_path(args)
    bank = args.bank
    rules = load_rules(args.rules) if args.rules else None
    report = import_bank_csv(
        bank,
        path,
        account=args.account,
        invert=args.invert,
        rules=rules,
        force_category=(args.category or "").strip(),
        dry_run=args.dry_run,
    )
    mode = "Dry run:" if report.dry_run else "Imported:"
    print(
        f"{mode} {len(report.added)} new entries from {report.source_file}"
        f" into {path} (account: {report.account})"
    )
    for entry in report.added:
        print(f"  {entry.date} {money(entry.amount):>11} {entry.category or '-':<20} {entry.description}")
    notes = []
    if report.duplicates:
        notes.append(f"{report.duplicates} duplicate(s) skipped")
    if report.skipped_rows:
        notes.append(f"{report.skipped_rows} blank/zero row(s) skipped")
    if notes:
        print("  (" + "; ".join(notes) + ")")
    if report.categorized:
        print(f"  auto-categorized {report.categorized} row(s) using rules")
    if report.dry_run:
        print("  dry run: nothing was written.")
    return 0


def cmd_categorize(args: argparse.Namespace) -> int:
    path = _ledger_path(args)
    rules = load_rules(args.rules)
    entries = load_ledger(path)
    changed = apply_rules(entries, rules)
    if not changed:
        print(f"No uncategorized entries matched any rule in {args.rules}.")
        return 0
    if not args.dry_run:
        save_ledger(path, entries)
    prefix = "Would categorize" if args.dry_run else "Auto-categorized"
    print(f"{prefix} {changed} entry(ies) using {args.rules}.")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    path = _ledger_path(args)
    month = args.month
    year = args.year
    if month is None and year is None:
        month = _date.today().strftime("%Y-%m")
        print(f"No --month/--year given; showing the current month ({month}).\n")
    if month is not None:
        if len(month) != 7 or not month[:4].isdigit() or not month[5:7].isdigit():
            raise CliError(f"Invalid month {month!r}: use YYYY-MM, e.g. 2026-10.")
        try:
            _date.fromisoformat(f"{month}-01")
        except ValueError as exc:
            raise CliError(f"Invalid month {month!r}: not a real month.") from exc
    if year is not None:
        if not year.isdigit() or len(year) != 4:
            raise CliError(f"Invalid year {year!r}: use YYYY, e.g. 2026.")
    entries = load_ledger(path)
    scoped = filter_entries(entries, month=month, year=year)
    summary = summarize(scoped)
    if month:
        title = f"Cashflow summary for {month} ({path})"
        print(render_summary(title, summary))
    else:
        title = f"Cashflow summary for {year} ({path})"
        breakdown = monthly_breakdown(scoped)
        print(render_summary(title, summary, monthly=breakdown))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    path = _ledger_path(args)
    month = args.month
    year = args.year
    if month is not None:
        if len(month) != 7 or month[4] != "-" or not month[:4].isdigit() or not month[5:7].isdigit():
            raise CliError(f"Invalid month {month!r}: use YYYY-MM, e.g. 2026-10.")
    if year is not None:
        if not year.isdigit() or len(year) != 4:
            raise CliError(f"Invalid year {year!r}: use YYYY, e.g. 2026.")
    entries = load_ledger(path)
    entries = filter_entries(entries, month=month, year=year)
    if args.category is not None:
        wanted = args.category.strip().casefold()
        entries = [e for e in entries if e.category.casefold() == wanted]
    if args.uncategorized:
        entries = [e for e in entries if not e.category]
    entries = sorted(entries, key=lambda e: (e.date, e.id))
    suffix = " [filtered]" if month or year or args.category or args.uncategorized else ""
    print(f"{len(entries)} entry(ies) in {path}{suffix}")
    for entry in entries:
        amount = money(entry.amount)
        print(
            f"{entry.date}  {entry.account:<12}  {entry.category or 'Uncategorized':<20}"
            f"  {amount:>12}  {entry.description}"
        )
    return 0


def cmd_tax_export(args: argparse.Namespace) -> int:
    path = _ledger_path(args)
    year_text = str(args.year).strip()
    if not year_text.isdigit() or len(year_text) != 4 or not 1900 <= int(year_text) <= 2999:
        raise CliError(f"Invalid year {args.year!r}: use a four-digit year, e.g. 2026.")
    year = int(year_text)
    exclude = [part.strip() for part in (args.exclude or "").split(",") if part.strip()]
    entries = load_ledger(path)
    lines = tax_lines(entries, year, exclude_categories=tuple(exclude))
    if args.output:
        write_tax_csv(args.output, lines)
        income, expenses = tax_totals(lines)
        print(f"Wrote {len(lines)} tax line(s) for {year} to {args.output}.")
        print(f"Income: {money(income)}  Expenses: {money(expenses)}  Net: {money(income - expenses)}")
        if exclude:
            print(f"Excluded categories: {', '.join(exclude)}")
    else:
        sys.stdout.write(tax_csv_text(lines))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (CliError, LedgerError, RulesError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
