from decimal import Decimal

from cashflow.tax import tax_csv_text, tax_lines, tax_totals
from tests.conftest import entry


def entries():
    return [
        entry(date="2025-12-25", amount="100.00", description="Last year", category="Book Sales"),
        entry(date="2026-01-15", amount="105.20", description="KDP ROYALTY PAYOUT", category="Book Royalties"),
        entry(date="2026-03-03", amount="-24.97", description="STAPLES", category="Office Supplies"),
        entry(date="2026-03-05", amount="-200.00", description="ONLINE TRANSFER", category="Transfers"),
        entry(date="2027-02-02", amount="9.99", description="Future", category="Book Sales"),
    ]


class TestTaxLines:
    def test_year_filter_and_types(self):
        lines = tax_lines(entries(), 2026)
        assert [(line.description, line.type) for line in lines] == [
            ("KDP ROYALTY PAYOUT", "income"),
            ("STAPLES", "expense"),
            ("ONLINE TRANSFER", "expense"),
        ]
        assert all(line.amount == Decimal(line.amount).quantize(Decimal("0.01")) for line in lines)

    def test_exclude_categories(self):
        lines = tax_lines(entries(), 2026, exclude_categories=("Transfers",))
        assert [(line.description, line.category) for line in lines] == [
            ("KDP ROYALTY PAYOUT", "Book Royalties"),
            ("STAPLES", "Office Supplies"),
        ]

    def test_exclude_case_insensitive_with_spaces(self):
        lines = tax_lines(entries(), 2026, exclude_categories=(" transfers ", "office supplies"))
        assert [line.description for line in lines] == ["KDP ROYALTY PAYOUT"]

    def test_uncategorized_included(self):
        mixed = entries() + [entry(date="2026-06-06", amount="5.00", description="MYSTERY")]
        lines = tax_lines(mixed, 2026)
        assert lines[-1].category == "Uncategorized" or lines[-1].category == ""

    def test_totals(self):
        income, expenses = tax_totals(tax_lines(entries(), 2026, exclude_categories=("Transfers",)))
        assert income == Decimal("105.20")
        assert expenses == Decimal("24.97")


class TestTaxCsv:
    def test_text_has_header_and_rows(self):
        text = tax_csv_text(tax_lines(entries(), 2026, exclude_categories=("Transfers",)))
        rows = text.strip().splitlines()
        assert rows[0] == "date,description,category,amount,type"
        assert rows[1].endswith("105.20,income")
        assert rows[2].endswith("-24.97,expense")
        assert len(rows) == 3

    def test_empty_ledger_is_header_only(self):
        text = tax_csv_text(tax_lines([], 2026))
        assert text.strip() == "date,description,category,amount,type"
