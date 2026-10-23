"""Tax-season export: a clean CSV limited to a tax year, ready for your CPA.

Money moved between your own accounts is not income or expense, so any
categories the user marks (typically ``Transfers``) are excluded.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal

from .ledger import Entry, cents

TAX_HEADERS = ["date", "description", "category", "amount", "type"]


@dataclass
class TaxLine:
    date: str
    description: str
    category: str
    amount: Decimal
    type: str


def tax_lines(
    entries: list[Entry],
    year: int,
    exclude_categories: tuple[str, ...] = (),
) -> list[TaxLine]:
    """Tax-relevant entries for ``year``, excluding the given categories."""
    excluded = {category.strip().casefold() for category in exclude_categories if category.strip()}
    lines: list[TaxLine] = []
    for entry in sorted(entries, key=lambda e: (e.date, e.description.casefold())):
        if not entry.date.startswith(f"{year:04d}-"):
            continue
        category_name = entry.category
        if category_name.casefold() in excluded:
            continue
        amount = cents(entry.amount)
        if amount == 0:
            continue
        lines.append(
            TaxLine(
                date=entry.date,
                description=entry.description,
                category=category_name,
                amount=amount,
                type="income" if amount > 0 else "expense",
            )
        )
    return lines


def tax_line_row(line: TaxLine) -> dict[str, str]:
    """CSV row for a tax line."""
    return {
        "date": line.date,
        "description": line.description,
        "category": line.category,
        "amount": f"{line.amount:.2f}",
        "type": line.type,
    }


def tax_totals(lines: list[TaxLine]) -> tuple[Decimal, Decimal]:
    """(total income, total expenses as a positive amount) across the lines."""
    income = Decimal("0.00")
    expenses = Decimal("0.00")
    for line in lines:
        if line.amount > 0:
            income += line.amount
        else:
            expenses += -line.amount
    return cents(income), cents(expenses)


def write_tax_csv(path: str, lines: list[TaxLine]) -> None:
    """Write the tax CSV to ``path``."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=TAX_HEADERS)
        writer.writeheader()
        for line in lines:
            writer.writerow(tax_line_row(line))


def tax_csv_text(lines: list[TaxLine]) -> str:
    """The same tax CSV as a string (for stdout export)."""
    import io

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=TAX_HEADERS)
    writer.writeheader()
    for line in lines:
        writer.writerow(tax_line_row(line))
    return buffer.getvalue()
