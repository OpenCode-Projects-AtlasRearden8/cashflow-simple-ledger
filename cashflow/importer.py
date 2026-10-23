"""Import bank CSV exports (date, amount, description) into a ledger.

The importer is deliberately tolerant about the CSV dialect (BOM, stray
columns, "$" and thousands separators, "(12.50)" negatives) but strict about
the three columns it needs: date, amount, description.

Dedupe: every parsed row is fingerprinted exactly like ledger entries, so a
re-downloaded export is recognized as a no-op instead of double-counted.
Rows are validated fully before anything is saved, so a bad row never leaves
the file half-imported.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .ledger import (
    Entry,
    LedgerError,
    load_ledger,
    norm_header,
    parse_amount,
    save_ledger,
    validate_date,
)
from .rules import Rule, find_category

REQUIRED_COLUMNS = ("date", "amount", "description")


@dataclass
class ImportReport:
    """What happened during an import attempt."""

    added: list[Entry] = field(default_factory=list)
    duplicates: int = 0
    skipped_rows: int = 0
    total_rows: int = 0
    categorized: int = 0
    account: str = ""
    source_file: str = ""
    dry_run: bool = False


def import_bank_csv(
    bank_path: str | os.PathLike,
    ledger_path: str | os.PathLike,
    *,
    account: str | None = None,
    invert: bool = False,
    rules: list[Rule] | None = None,
    force_category: str = "",
    dry_run: bool = False,
) -> ImportReport:
    """Merge a bank CSV into the ledger, skipping duplicates.

    ``invert`` flips amount signs for banks that export debits as positive
    numbers. ``rules`` auto-categorizes imported rows. ``account`` defaults
    to the bank file's stem, which also keeps fingerprints stable across
    repeated downloads of the same account.
    """
    bank_path = Path(bank_path).expanduser()
    try:
        fh = open(bank_path, newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise LedgerError(f"Could not open bank file {bank_path}: {exc.strerror or exc}") from exc
    with fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise LedgerError(f"{bank_path} has no CSV header row; expected columns date, amount, description.")
        lookup = {h.replace("\ufeff", "").strip().lower(): h for h in reader.fieldnames}
        missing = [column for column in REQUIRED_COLUMNS if column not in lookup]
        if missing:
            raise LedgerError(
                f"{bank_path} is missing required column(s) {', '.join(missing)};"
                f" found {', '.join(reader.fieldnames)}."
            )
        account_name = (account or "").strip() or bank_path.stem
        imported: list[Entry] = []
        seen: set[str] = set()
        report = ImportReport(account=account_name, source_file=bank_path.name, dry_run=dry_run)
        for lineno, row in enumerate(reader, start=2):
            row = {norm_header(name if isinstance(name, str) else ""): ("" if value is None else str(value).strip()) for name, value in row.items() if name is not None}
            if not any(row[column] for column in REQUIRED_COLUMNS):
                continue
            report.total_rows += 1
            try:
                date_text = validate_date(row["date"])
                amount = parse_amount(row["amount"])
            except LedgerError as exc:
                raise LedgerError(f"{bank_path} line {lineno}: {exc}") from exc
            description = row["description"]
            if not description:
                raise LedgerError(f"{bank_path} line {lineno}: description is empty.")
            if amount == 0:
                report.skipped_rows += 1
                continue
            if invert:
                amount = -amount
            entry = Entry(
                date=date_text,
                amount=amount,
                description=description,
                category=force_category,
                account=account_name,
                source=bank_path.name,
            )
            ruled_category = None
            if rules and not entry.category:
                ruled_category = find_category(rules, description)
                if ruled_category:
                    entry.category = ruled_category
            if entry.id in seen:
                report.duplicates += 1
                continue
            seen.add(entry.id)
            if ruled_category:
                report.categorized += 1
            imported.append(entry)

    existing = load_ledger(ledger_path)
    existing_ids = {entry.id for entry in existing}
    fresh = [entry for entry in imported if entry.id not in existing_ids]
    report.duplicates += len(imported) - len(fresh)
    report.added = fresh
    if fresh and not dry_run:
        save_ledger(ledger_path, existing + fresh)
    return report
