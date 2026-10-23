from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from cashflow import cli
from cashflow.ledger import load_ledger

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_BANK = str(ROOT / "sample-data" / "bank-export.csv")
SAMPLE_CARD = str(ROOT / "sample-data" / "credit-card.csv")
SAMPLE_RULES = str(ROOT / "sample-data" / "rules.csv")


def run(capsys, *args):
    code = cli.main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


class TestInit:
    def test_creates_file(self, capsys, tmp_cwd):
        code, out, _ = run(capsys, "init")
        assert code == 0
        assert "Created empty ledger file: ledger.csv" in out
        assert (tmp_cwd / "ledger.csv").read_text(encoding="utf-8").startswith("id,date,amount,description,category,account,source")

    def test_refuses_existing(self, capsys, tmp_cwd):
        run(capsys, "init")
        code, _, err = run(capsys, "init")
        assert code == 1
        assert "already exists" in err

    def test_custom_file_before_and_after_subcommand(self, capsys, tmp_cwd):
        code, _, _ = run(capsys, "--file", "main.csv", "init")
        assert code == 0
        assert (tmp_cwd / "main.csv").exists()
        code, _, _ = run(capsys, "init", "-f", "other.csv")
        assert code == 0
        assert (tmp_cwd / "other.csv").exists()


class TestAdd:
    def test_add_expense(self, capsys, tmp_cwd):
        run(capsys, "init")
        code, out, _ = run(capsys, "add", "2026-10-05", "-6.99", "Pens and sticky notes", "-c", "Office Supplies")
        assert code == 0
        assert "Added: 2026-10-05 -$6.99" in out
        entries = load_ledger("ledger.csv")
        assert len(entries) == 1
        assert entries[0].amount == Decimal("-6.99")
        assert entries[0].category == "Office Supplies"
        assert entries[0].account == "cash"

    def test_add_zero_amount_rejected(self, capsys, tmp_cwd):
        run(capsys, "init")
        code, _, err = run(capsys, "add", "2026-10-05", "0", "Nothing")
        assert code == 1
        assert "cannot be zero" in err

    def test_add_bad_date_rejected(self, capsys, tmp_cwd):
        run(capsys, "init")
        code, _, err = run(capsys, "add", "2026-02-30", "-1", "Bad date")
        assert code == 1
        assert "not a real calendar date" in err

    def test_add_duplicate_rejected(self, capsys, tmp_cwd):
        run(capsys, "init")
        run(capsys, "add", "2026-10-05", "-6.99", "Pens")
        code, _, err = run(capsys, "add", "2026-10-05", "-6.99", "PENS")
        assert code == 1
        assert "Duplicate entry" in err
        assert len(load_ledger("ledger.csv")) == 1

    def test_add_case_insensitive_duplicate(self, capsys, tmp_cwd):
        run(capsys, "init")
        run(capsys, "add", "2026-10-05", "-6.99", "office pens")
        code, _, _ = run(capsys, "add", "2026-10-05", "-6.99", "OFFICE PENS")
        assert code == 1


class TestImportCommand:
    def test_import_with_rules_and_dedupe(self, capsys, tmp_cwd):
        run(capsys, "init")
        code, out, _ = run(capsys, "import", SAMPLE_BANK, "--account", "checking", "--rules", SAMPLE_RULES)
        assert code == 0
        assert "12 new entries" in out
        assert "1 duplicate(s) skipped" in out
        code, out, _ = run(capsys, "import", SAMPLE_BANK, "--account", "checking")
        assert code == 0
        assert "0 new entries" in out
        assert "13 duplicate(s) skipped" in out
        assert len(load_ledger("ledger.csv")) == 12

    def test_dry_run_writes_nothing(self, capsys, tmp_cwd):
        run(capsys, "init")
        code, out, _ = run(capsys, "import", SAMPLE_BANK, "-n")
        assert code == 0
        assert "Dry run:" in out
        assert "nothing was written" in out
        assert load_ledger("ledger.csv") == []

    def test_missing_bank_file(self, capsys, tmp_cwd):
        run(capsys, "init")
        code, _, err = run(capsys, "import", "ghost.csv")
        assert code == 1
        assert "Could not open" in err

    def test_second_account_keeps_records_separate(self, capsys, tmp_cwd):
        run(capsys, "init")
        run(capsys, "import", SAMPLE_BANK, "--account", "checking")
        code, out, _ = run(capsys, "import", SAMPLE_CARD, "--account", "creditcard")
        assert code == 0
        assert "2 new entries" in out
        entries = load_ledger("ledger.csv")
        assert len(entries) == 14
        assert {e.account for e in entries} == {"checking", "creditcard"}


class TestCategorizeCommand:
    def seed(self, capsys, tmp_cwd):
        run(capsys, "init")
        run(capsys, "add", "2026-10-05", "-19.97", "ADOBE CC LITE MO")
        run(capsys, "add", "2026-10-06", "-3.50", "UNKNOWN THING")

    def test_categorizes_with_rules(self, capsys, tmp_cwd):
        self.seed(capsys, tmp_cwd)
        code, out, _ = run(capsys, "categorize", "-r", SAMPLE_RULES)
        assert code == 0
        assert "1 entry(ies)" in out
        entries = load_ledger("ledger.csv")
        assert [e.category for e in entries] == ["Software", ""]

    def test_missing_rules_file_hint(self, capsys, tmp_cwd):
        self.seed(capsys, tmp_cwd)
        code, _, err = run(capsys, "categorize")
        assert code == 1
        assert "not found" in err
        assert "--rules" in err

    def test_dry_run_leaves_alone(self, capsys, tmp_cwd):
        self.seed(capsys, tmp_cwd)
        code, out, _ = run(capsys, "categorize", "-r", SAMPLE_RULES, "-n")
        assert code == 0
        assert "Would categorize" in out
        entries = load_ledger("ledger.csv")
        assert [e.category for e in entries] == ["", ""]


class TestSummaryCommand:
    def seeded_ledger(self, capsys, tmp_cwd):
        run(capsys, "init")
        run(capsys, "import", SAMPLE_BANK, "--account", "checking", "--rules", SAMPLE_RULES)

    def test_month_summary(self, capsys, tmp_cwd):
        self.seeded_ledger(capsys, tmp_cwd)
        code, out, _ = run(capsys, "summary", "--month", "2026-10")
        assert code == 0
        assert "Cashflow summary for 2026-10" in out
        assert "Income:    $249.94" in out
        assert "Expenses:  $441.74" in out
        assert "Book Royalties" in out

    def test_year_summary_has_monthly_table(self, capsys, tmp_cwd):
        self.seeded_ledger(capsys, tmp_cwd)
        run(capsys, "add", "2026-09-30", "50.00", "Old income")
        code, out, _ = run(capsys, "summary", "-y", "2026")
        assert code == 0
        assert "Cashflow summary for 2026" in out
        assert "By month:" in out
        assert "2026-09" in out and "2026-10" in out

    def test_empty_month(self, capsys, tmp_cwd):
        run(capsys, "init")
        run(capsys, "add", "2026-10-05", "-1.00", "Only")
        code, out, _ = run(capsys, "summary", "--month", "2025-12")
        assert code == 0
        assert "Entries:   0" in out

    def test_invalid_month(self, capsys, tmp_cwd):
        self.seeded_ledger(capsys, tmp_cwd)
        code, _, err = run(capsys, "summary", "--month", "2026-13")
        assert code == 1
        assert "Invalid month" in err

    def test_invalid_year(self, capsys, tmp_cwd):
        self.seeded_ledger(capsys, tmp_cwd)
        code, _, err = run(capsys, "summary", "--year", "abcd")
        assert code == 1
        assert "Invalid year" in err


class TestListCommand:
    def test_list_filters(self, capsys, tmp_cwd):
        run(capsys, "init")
        run(capsys, "import", SAMPLE_BANK, "--account", "checking", "--rules", SAMPLE_RULES)
        code, out, _ = run(capsys, "list", "--month", "2026-10", "--category", "software")
        assert code == 0
        assert "3 entry(ies)" in out
        assert "ADOBE CC LITE MO 850588" in out
        code, out, _ = run(capsys, "list", "-u")
        assert code == 0
        assert "0 entry(ies)" in out

    def test_list_show_uncategorized(self, capsys, tmp_cwd):
        run(capsys, "init")
        run(capsys, "add", "2026-10-05", "-1.00", "Mystery cash")
        code, out, _ = run(capsys, "list", "-u")
        assert code == 0
        assert "Mystery cash" in out
        assert "Uncategorized" in out


class TestTaxExportCommand:
    def test_stdout_is_pure_csv(self, capsys, tmp_cwd):
        run(capsys, "init")
        run(capsys, "import", SAMPLE_BANK, "--account", "checking", "--rules", SAMPLE_RULES)
        code, out, _ = run(capsys, "tax-export", "2026", "--exclude", "Transfers")
        assert code == 0
        lines = out.strip().splitlines()
        assert lines[0] == "date,description,category,amount,type"
        assert len(lines) == 12  # 11 data rows + header
        assert "Transfers" not in out

    def test_output_file_and_totals(self, capsys, tmp_cwd):
        run(capsys, "init")
        run(capsys, "import", SAMPLE_BANK, "--account", "checking", "--rules", SAMPLE_RULES)
        code, out, _ = run(capsys, "tax-export", "2026", "--exclude", "Transfers", "-o", "tax-2026.csv")
        assert code == 0
        assert "Wrote 11 tax line(s) for 2026 to tax-2026.csv" in out
        assert "Net: $8.20" in out
        assert (tmp_cwd / "tax-2026.csv").read_text(encoding="utf-8").startswith("date,description,category,amount,type")

    def test_invalid_year(self, capsys, tmp_cwd):
        run(capsys, "init")
        code, _, err = run(capsys, "tax-export", "26")
        assert code == 1
        assert "Invalid year" in err


class TestModuleEntry:
    def test_python_dash_m_version(self, tmp_path):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        result = subprocess.run(
            [sys.executable, "-m", "cashflow", "--version"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0
        assert "cashflow 0.1.0" in result.stdout

    def test_python_dash_m_workflow(self, tmp_path):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        commands = [
            ["init"],
            ["add", "2026-10-05", "-6.99", "Pens", "-c", "Office Supplies"],
            ["summary", "--month", "2026-10"],
        ]
        for command in commands:
            result = subprocess.run(
                [sys.executable, "-m", "cashflow", *command],
                cwd=tmp_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, result.stderr
        assert (tmp_path / "ledger.csv").exists()

    def test_no_subcommand_exits_nonzero(self):
        with pytest.raises(SystemExit) as excinfo:
            cli.main([])
        assert excinfo.value.code != 0
