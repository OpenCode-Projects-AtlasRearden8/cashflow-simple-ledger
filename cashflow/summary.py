"""Monthly and yearly cashflow summaries."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .ledger import Entry, cents


def money(amount: Decimal) -> str:
    """Format a Decimal with a $ sign; keep the minus sign in front."""
    amount = cents(amount)
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


@dataclass
class Summary:
    """Totals for a set of entries, grouped by category."""

    entries: list[Entry] = field(default_factory=list)
    income: Decimal = Decimal("0.00")
    expenses: Decimal = Decimal("0.00")
    income_by_category: dict[str, Decimal] = field(default_factory=dict)
    expense_by_category: dict[str, Decimal] = field(default_factory=dict)

    @property
    def net(self) -> Decimal:
        return cents(self.income) - cents(self.expenses)

    @property
    def count(self) -> int:
        return len(self.entries)


def filter_entries(entries: list[Entry], month: str | None = None, year: str | None = None) -> list[Entry]:
    """Keep only entries for a month (YYYY-MM) and/or a year (YYYY)."""
    return [
        entry
        for entry in entries
        if (month is None or entry.date.startswith(month + "-"))
        and (year is None or entry.date.startswith(year + "-"))
    ]


def summarize(entries: list[Entry]) -> Summary:
    """Totals plus per-category breakdown; sign splits income vs expenses."""
    result = Summary(entries=entries)
    for entry in entries:
        amount = cents(entry.amount)
        if amount > 0:
            result.income += amount
            result.income_by_category[entry.category] = result.income_by_category.get(entry.category, Decimal("0.00")) + amount
        elif amount < 0:
            result.expenses += -amount
            result.expense_by_category[entry.category] = result.expense_by_category.get(entry.category, Decimal("0.00")) + -amount
    return result


def monthly_breakdown(entries: list[Entry]) -> list[tuple[str, Decimal, Decimal]]:
    """Per-month (YYYY-MM, income, expenses) for the entries in chronological order."""
    totals: dict[str, list[Decimal]] = {}
    for entry in entries:
        month = entry.date[:7]
        amount = cents(entry.amount)
        bucket = totals.setdefault(month, [Decimal("0.00"), Decimal("0.00")])
        if amount > 0:
            bucket[0] += amount
        elif amount < 0:
            bucket[1] += -amount
    return [(month, bucket[0], bucket[1]) for month, bucket in sorted(totals.items())]


def _by_category_line(name: str, amount: Decimal) -> str:
    label = name if name else "Uncategorized"
    return f"  {label:<24} {money(amount):>12}"


def render_summary(title: str, summary: Summary, monthly: list[tuple[str, Decimal, Decimal]] | None = None) -> str:
    """Human-readable summary block used by the ``summary`` command."""
    lines = [
        title,
        f"Entries:   {summary.count}",
        f"Income:    {money(summary.income)}",
        f"Expenses:  {money(summary.expenses)}",
        f"Net:       {money(summary.net)}",
        "",
    ]
    if summary.income_by_category:
        lines.append("Income by category:")
        for category, amount in sorted(summary.income_by_category.items()):
            lines.append(_by_category_line(category, amount))
        lines.append("")
    if summary.expense_by_category:
        lines.append("Expenses by category:")
        for category, amount in sorted(summary.expense_by_category.items()):
            lines.append(_by_category_line(category, amount))
        lines.append("")
    if monthly:
        lines.append("By month:")
        for month, income, expenses in monthly:
            lines.append(f"  {month}  income {money(income):>12}  expenses {money(expenses):>12}")
        lines.append("")
    return "\n".join(lines).rstrip()
