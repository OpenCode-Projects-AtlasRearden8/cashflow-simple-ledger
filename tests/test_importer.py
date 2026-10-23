from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from cashflow import importer, rules as rules_mod
from cashflow.ledger import load_ledger
from tests.conftest import write_text

RULES_CSV = Path(__file__).resolve().parent.parent / "sample-data" / "rules.csv"


@pytest.fixture
def rules():
    return rules_mod.load_rules(RULES_CSV)


def sample(tmp_path, rows: str) -> str:
    content = "date,amount,description\n" + rows
    return str(write_text(tmp_path / "bank-export.csv", content))


class TestImport:
    def test_basic_import(self, tmp_path, tmp_cwd):
        bank = sample(tmp_path, "2026-10-03,-24.97,STAPLES OFFICE SUPPLIES\n2026-10-05,10.00,REFUND\n")
        report = importer.import_bank_csv(bank, "ledger.csv")
        assert [entry.description for entry in report.added] == ["STAPLES OFFICE SUPPLIES", "REFUND"]
        assert report.account == "bank-export"
        assert report.source_file == "bank-export.csv"
        assert report.total_rows == 2
        entries = load_ledger("ledger.csv")
        assert len(entries) == 2
        assert entries[0].account == "bank-export"
        assert entries[0].source == "bank-export.csv"

    def test_amount_formats(self, tmp_path, tmp_cwd):
        bank = sample(tmp_path, '2026-10-03,(12.50),PAREN NEG\n2026-10-04,"$1,234.50",WIDE AMT\n')
        report = importer.import_bank_csv(bank, "ledger.csv")
        amounts = [entry.amount for entry in report.added]
        assert amounts == [Decimal("-12.50"), Decimal("1234.50")]

    def test_extra_columns_ignored(self, tmp_path, tmp_cwd):
        path = tmp_path / "bank.csv"
        path.write_text("date,amount,description,extra\n2026-10-03,1.00,Something,ignored\n", encoding="utf-8")
        report = importer.import_bank_csv(path, "ledger.csv")
        assert len(report.added) == 1

    def test_case_insensitive_headers(self, tmp_path, tmp_cwd):
        path = tmp_path / "bank.csv"
        path.write_text("Date,Amount,Description\n2026-10-03,1.00,Something\n", encoding="utf-8")
        report = importer.import_bank_csv(path, "ledger.csv")
        assert len(report.added) == 1

    def test_blank_and_zero_rows_skipped(self, tmp_path, tmp_cwd):
        bank = sample(tmp_path, "2026-10-03,0.00,ZERO\n\n2026-10-04,1.00,REAL\n")
        report = importer.import_bank_csv(bank, "ledger.csv")
        assert len(report.added) == 1
        assert report.skipped_rows == 1

    def test_invert_flag(self, tmp_path, tmp_cwd):
        bank = sample(tmp_path, "2026-10-03,49.99,DEBIT AS POSITIVE\n")
        report = importer.import_bank_csv(bank, "ledger.csv", invert=True)
        assert report.added[0].amount == Decimal("-49.99")


class TestDedupe:
    def test_internal_duplicate_row_skipped(self, tmp_path, tmp_cwd):
        row = "2026-10-19,-6.99,ADOBE CC LITE MO 850588\n"
        bank = sample(tmp_path, row + row)
        report = importer.import_bank_csv(bank, "ledger.csv")
        assert len(report.added) == 1
        assert report.duplicates == 1

    def test_reimport_same_file_is_noop(self, tmp_path, tmp_cwd):
        bank = sample(tmp_path, "2026-10-19,-6.99,ADOBE CC LITE MO\n2026-10-20,105.20,KDP ROYALTY PAYOUT\n")
        first = importer.import_bank_csv(bank, "ledger.csv")
        assert len(first.added) == 2
        second = importer.import_bank_csv(bank, "ledger.csv")
        assert second.added == []
        assert second.duplicates == 2
        assert len(load_ledger("ledger.csv")) == 2

    def test_import_after_manual_entry_dedupes(self, tmp_path, tmp_cwd):
        from cashflow.ledger import Entry, append_entry

        append_entry("ledger.csv", Entry(date="2026-10-19", amount=Decimal("-6.99"), description="ADOBE CC LITE MO", account="bank-export"))
        bank = sample(tmp_path, "2026-10-19,-6.99,ADOBE CC LITE MO\n")
        report = importer.import_bank_csv(bank, "ledger.csv")
        assert report.added == []
        assert report.duplicates == 1


class TestCategorizationOnImport:
    def test_rules_applied(self, tmp_path, tmp_cwd, rules):
        bank = sample(tmp_path, "2026-10-03,-24.97,STAPLES OFFICE SUPPLIES\n2026-10-05,-9.99,SOMETHING ELSE\n")
        report = importer.import_bank_csv(bank, "ledger.csv", rules=rules)
        assert [entry.category for entry in report.added] == ["Office Supplies", ""]
        assert report.categorized == 1

    def test_force_category(self, tmp_path, tmp_cwd):
        bank = sample(tmp_path, "2026-10-03,-1.99,ANYTHING\n")
        report = importer.import_bank_csv(bank, "ledger.csv", force_category="Transfers")
        assert report.added[0].category == "Transfers"


class TestValidation:
    def test_bad_date_aborts(self, tmp_path, tmp_cwd):
        bank = sample(tmp_path, "2026-10-03,-1.00,OK\n2026-10-33,-1.00,BAD\n")
        with pytest.raises(importer.LedgerError, match="line 3"):
            importer.import_bank_csv(bank, "ledger.csv")
        assert not (tmp_cwd / "ledger.csv").exists()

    def test_bad_amount_aborts(self, tmp_path, tmp_cwd):
        bank = sample(tmp_path, "2026-10-03,,NOMONEY\n")
        with pytest.raises(importer.LedgerError, match="Amount is missing"):
            importer.import_bank_csv(bank, "ledger.csv")
        assert not (tmp_cwd / "ledger.csv").exists()

    def test_empty_description_aborts(self, tmp_path, tmp_cwd):
        bank = sample(tmp_path, "2026-10-03,-1.00, \n")
        with pytest.raises(importer.LedgerError, match="description is empty"):
            importer.import_bank_csv(bank, "ledger.csv")

    def test_missing_columns(self, tmp_path, tmp_cwd):
        path = tmp_path / "bank.csv"
        path.write_text("date,description\n2026-10-03,Something\n", encoding="utf-8")
        with pytest.raises(importer.LedgerError, match="amount"):
            importer.import_bank_csv(path, "ledger.csv")

    def test_missing_bank_file(self, tmp_path, tmp_cwd):
        with pytest.raises(importer.LedgerError, match="Could not open"):
            importer.import_bank_csv(tmp_path / "ghost.csv", "ledger.csv")

    def test_dry_run_writes_nothing(self, tmp_path, tmp_cwd):
        bank = sample(tmp_path, "2026-10-03,-1.00,OK\n")
        report = importer.import_bank_csv(bank, "ledger.csv", dry_run=True)
        assert len(report.added) == 1
        assert report.dry_run
        assert not (tmp_cwd / "ledger.csv").exists()

    def test_dry_run_keeps_existing_ledger(self, tmp_path, tmp_cwd):
        bank = sample(tmp_path, "2026-10-03,-1.00,OK\n")
        importer.import_bank_csv(bank, "ledger.csv")
        before = (tmp_cwd / "ledger.csv").read_text(encoding="utf-8")
        report = importer.import_bank_csv(bank, "ledger.csv", dry_run=True)
        assert report.added == []
        assert (tmp_cwd / "ledger.csv").read_text(encoding="utf-8") == before
