"""Ledger storage: a portable, dedupe-aware CSV file of cashflow entries.

The ledger is a plain CSV with a stable header so it can be opened in any
spreadsheet, synced across machines, and versioned in git:

    id,date,amount,description,category,account,source

Conventions:
    * dates are ISO ``YYYY-MM-DD`` strings
    * amounts are signed 2-decimal strings (positive = income, negative = expense)
    * ``category`` may be empty (shown as "Uncategorized"); the ``Transfers``
      convention marks money moved between your own accounts
    * ``id`` is a deterministic fingerprint of (date, amount, description,
      account). Two identical transactions always produce the same id, which
      is what makes dedupe portable across copies of the ledger.
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

DEFAULT_FILE = "ledger.csv"
DEFAULT_ACCOUNT = "cash"
MANUAL_SOURCE = "manual"
LEDGER_HEADERS = ["id", "date", "amount", "description", "category", "account", "source"]
CENT = Decimal("0.01")
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


class LedgerError(Exception):
    """A ledger file or entry is invalid."""


class DuplicateEntryError(LedgerError):
    """An entry with the same fingerprint already exists in the ledger."""


@dataclass
class Entry:
    """One money movement in or out of a tracked account."""

    date: str
    amount: Decimal
    description: str
    category: str = ""
    account: str = DEFAULT_ACCOUNT
    source: str = MANUAL_SOURCE
    id: str = ""

    def __post_init__(self) -> None:
        self.date = str(self.date).strip()
        self.description = str(self.description).strip()
        self.category = str(self.category).strip()
        self.account = str(self.account).strip()
        if not self.id:
            self.id = entry_id(self.date, self.amount, self.description, self.account)


def cents(amount: Decimal | str | int) -> Decimal:
    """Round a value to exactly two decimal places (half-up, like receipts)."""
    return Decimal(amount).quantize(CENT, rounding=ROUND_HALF_UP)


def entry_id(date_text: str, amount: Decimal, description: str, account: str) -> str:
    """Deterministic fingerprint used for portable, cross-copy dedupe."""
    key = "\x1f".join(
        [
            date_text,
            f"{amount:.2f}",
            description.strip().casefold(),
            account.strip().casefold(),
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def parse_amount(text: str | None) -> Decimal:
    """Parse a human/bank amount string to a signed Decimal in cents.

    Accepts "6.99", "-6.99", "$1,234.50", "(12.50)" (accounting negative) and
    plain integers. Raises :class:`LedgerError` for anything unparseable.
    """
    raw = "" if text is None else str(text).strip()
    if not raw:
        raise LedgerError("Amount is missing.")
    negative = False
    if raw.startswith("(") and raw.endswith(")"):
        negative = True
        raw = raw[1:-1]
    raw = raw.replace("$", "").replace(",", "").strip()
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise LedgerError(f"Could not parse amount {text!r}.") from exc
    if negative:
        value = -abs(value)
    return cents(value)


def validate_date(text: str | None) -> str:
    """Validate and normalize an ISO date (YYYY-MM-DD)."""
    raw = "" if text is None else str(text).strip()
    if not DATE_PATTERN.fullmatch(raw):
        raise LedgerError(f"Date {text!r} must be in YYYY-MM-DD format.")
    try:
        date.fromisoformat(raw)
    except ValueError as exc:
        raise LedgerError(f"Date {text!r} is not a real calendar date.") from exc
    return raw


def norm_header(header: str) -> str:
    """Normalize a CSV header cell for tolerant matching."""
    return str(header).replace("\ufeff", "").strip().lower()


def load_ledger(path: str | os.PathLike) -> list[Entry]:
    """Load all entries from a ledger CSV, or ``[]`` when it does not exist yet."""
    path = os.fspath(path)
    if not os.path.exists(path):
        return []
    entries: list[Entry] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return []
        headers = [norm_header(h) for h in reader.fieldnames]
        if headers != LEDGER_HEADERS:
            raise LedgerError(
                f"{path} is not a cashflow ledger file: expected header"
                f" {','.join(LEDGER_HEADERS)} but found {','.join(headers)}."
            )
        for lineno, row in enumerate(reader, start=2):
            clean = {k: ("" if v is None else str(v).strip()) for k, v in row.items() if k is not None}
            if not any(clean.get(name) for name in LEDGER_HEADERS):
                continue
            try:
                amount = Decimal(clean["amount"])
            except InvalidOperation as exc:
                raise LedgerError(f"{path} line {lineno}: bad amount {clean['amount']!r}.") from exc
            try:
                validate_date(clean["date"])
            except LedgerError as exc:
                raise LedgerError(f"{path} line {lineno}: {exc}") from exc
            if not clean["description"]:
                raise LedgerError(f"{path} line {lineno}: description is empty.")
            entries.append(
                Entry(
                    date=clean["date"],
                    amount=amount,
                    description=clean["description"],
                    category=clean["category"],
                    account=clean["account"],
                    source=clean["source"],
                    id=clean["id"],
                )
            )
    return entries


def entry_to_row(entry: Entry) -> dict[str, str]:
    """Convert an entry to the portable CSV row representation."""
    return {
        "id": entry.id,
        "date": entry.date,
        "amount": f"{cents(entry.amount):.2f}",
        "description": entry.description,
        "category": entry.category,
        "account": entry.account,
        "source": entry.source,
    }


def save_ledger(path: str | os.PathLike, entries: list[Entry]) -> None:
    """Write the ledger atomically, sorted by date then id (stable diffs)."""
    path = os.fspath(path)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".ledger-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=LEDGER_HEADERS)
            writer.writeheader()
            for entry in sorted(entries, key=lambda e: (e.date, e.id)):
                writer.writerow(entry_to_row(entry))
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    os.replace(tmp_path, path)


def append_entry(path: str | os.PathLike, entry: Entry) -> Entry:
    """Add one entry, refusing exact duplicates (same fingerprint id)."""
    entries = load_ledger(path)
    if any(existing.id == entry.id for existing in entries):
        raise DuplicateEntryError(
            f"Duplicate entry: {entry.date} {entry.amount:.2f} {entry.description!r}"
            f" (account {entry.account!r}) already exists."
        )
    entries.append(entry)
    save_ledger(path, entries)
    return entry
