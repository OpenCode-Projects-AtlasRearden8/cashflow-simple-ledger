from decimal import Decimal

from cashflow.ledger import Entry
from cashflow.summary import filter_entries, money, monthly_breakdown, render_summary, summarize
from tests.conftest import entry


def ledger_entries():
    return [
        entry(date="2026-10-02", amount="105.20", description="KDP payout", category="Book Royalties"),
        entry(date="2026-10-03", amount="-24.97", description="Staples", category="Office Supplies"),
        entry(date="2026-10-14", amount="89.99", description="Square", category="Book Sales"),
        entry(date="2026-11-01", amount="-9.99", description="Adobe", category="Software"),
        entry(date="2026-10-20", amount="-5.00", description="Mystery"),
    ]


class TestMoney:
    def test_positive_and_negative(self):
        assert money(Decimal("21.19")) == "$21.19"
        assert money(Decimal("-6.99")) == "-$6.99"
        assert money(Decimal("-0.50")) == "-$0.50"
        assert money(Decimal("0")) == "$0.00"

    def test_thousands_separators(self):
        assert money(Decimal("1234567.89")) == "$1,234,567.89"


class TestFilterEntries:
    def test_month(self):
        kept = filter_entries(ledger_entries(), month="2026-10")
        assert all(e.date.startswith("2026-10-") for e in kept)

    def test_year(self):
        kept = filter_entries(ledger_entries(), year="2026")
        assert len(kept) == 5

    def test_other_year_empty(self):
        assert filter_entries(ledger_entries(), year="2025") == []


class TestSummarize:
    def test_totals(self):
        summary = summarize(ledger_entries())
        assert summary.income == Decimal("195.19")
        assert summary.expenses == Decimal("39.96")
        assert summary.net == Decimal("155.23")
        assert summary.count == 5

    def test_by_category(self):
        summary = summarize(ledger_entries())
        assert summary.income_by_category == {
            "Book Royalties": Decimal("105.20"),
            "Book Sales": Decimal("89.99"),
        }
        assert summary.expense_by_category == {
            "Office Supplies": Decimal("24.97"),
            "Software": Decimal("9.99"),
            "": Decimal("5.00"),
        }

    def test_render_includes_categories_and_uncategorized(self):
        summary = summarize(filter_entries(ledger_entries(), month="2026-10"))
        text = render_summary("Cashflow summary for 2026-10", summary)
        assert "Cashflow summary for 2026-10" in text
        assert "Income:    $195.19" in text
        assert "Expenses:  $29.97" in text
        assert "Net:       $165.22" in text
        assert "Uncategorized" in text.replace("  ", " ") or "Uncategorized" in text


class TestMonthlyBreakdown:
    def test_only_months_with_data_sorted(self):
        rows = monthly_breakdown(ledger_entries())
        assert rows == [
            ("2026-10", Decimal("195.19"), Decimal("29.97")),
            ("2026-11", Decimal("0.00"), Decimal("9.99")),
        ]

    def test_render_with_monthly(self):
        rows = monthly_breakdown(ledger_entries())
        text = render_summary("Year", summarize(ledger_entries()), monthly=rows)
        assert "By month:" in text
        assert "2026-11  income" in text


def test_blank_ledger_summary():
    summary = summarize([])
    text = render_summary("Cashflow summary", summary)
    assert "Entries:   0" in text
    assert "$0.00" in text
