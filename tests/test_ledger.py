from __future__ import annotations

from decimal import Decimal

import pytest

from cashflow import ledger
from tests.conftest import entry


class TestEntryId:
    def test_deterministic(self):
        first = entry(date="2026-10-19", amount="-6.99", description="ADOBE CC LITE MO", account="checking").id
        second = entry(date="2026-10-19", amount="-6.99", description="ADOBE CC LITE MO", account="checking").id
        assert first == second
        assert len(first) == 16

    def test_case_and_whitespace_insensitive(self):
        upper = entry(date="2026-10-01", amount="5.00", description="AMZ PMTS", account="cash").id
        lower = entry(date="2026-10-01", amount="5.00", description="  amz pmts ", account=" cash ").id
        assert upper == lower

    def test_amount_precision_insensitive(self):
        two_decimals = entry(date="2026-10-01", amount="5.00", description="x").id
        three_decimals = entry(date="2026-10-01", amount="5.000", description="x").id
        assert two_decimals == three_decimals

    def test_differs_by_fields(self):
        base = dict(date="2026-10-01", description="coffee", account="cash")
        ids = {
            entry(amount="5.00", **base).id,
            entry(amount="-5.00", **base).id,
            entry(amount="5.01", **base).id,
            entry(date="2026-10-02", amount="5.00", description="coffee", account="cash").id,
            entry(date="2026-10-01", amount="5.00", description="coffee 2", account="cash").id,
            entry(date="2026-10-01", amount="5.00", description="coffee", account="checking").id,
        }
        assert len(ids) == 6


class TestParseAmount:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("6.99", "6.99"),
            ("-6.99", "-6.99"),
            ("$1,234.50", "1234.50"),
            ("(12.50)", "-12.50"),
            (" 5 ", "5.00"),
            ("0", "0.00"),
            ("+2.5", "2.50"),
            ("105.205", "105.21"),
        ],
    )
    def test_variants(self, text, expected):
        assert ledger.parse_amount(text) == Decimal(expected)

    @pytest.mark.parametrize("text", ["", None, "abc", "12.34.56", "$-"])
    def test_invalid(self, text):
        with pytest.raises(ledger.LedgerError):
            ledger.parse_amount(text)


class TestValidateDate:
    def test_valid(self):
        assert ledger.validate_date("2026-10-19") == "2026-10-19"

    @pytest.mark.parametrize("text", ["", "2026-10", "26-10-19", "2026-02-30", "not-a-date", "20261019"])
    def test_invalid(self, text):
        with pytest.raises(ledger.LedgerError):
            ledger.validate_date(text)


class TestLoadAndSave:
    def test_missing_file_is_empty(self, tmp_path):
        assert ledger.load_ledger(tmp_path / "nope.csv") == []

    def test_round_trip_sorted(self, tmp_path):
        path = tmp_path / "ledger.csv"
        older = entry(date="2026-10-01", amount="10.00", description="Older")
        newer = entry(date="2026-10-19", amount="-6.99", description="Newer")
        ledger.save_ledger(path, [newer, older])
        text = path.read_text(encoding="utf-8")
        assert text.splitlines()[0] == "id,date,amount,description,category,account,source"
        loaded = ledger.load_ledger(path)
        assert [e.description for e in loaded] == ["Older", "Newer"]
        assert loaded[0].amount == Decimal("10.00")
        assert loaded[0].id

    def test_load_preserves_all_fields(self, tmp_path):
        path = tmp_path / "ledger.csv"
        original = entry(
            date="2026-11-02",
            amount="-3.25",
            description="Bought a thing",
            category="Office Supplies",
            account="checking",
            source="bank-export.csv",
        )
        ledger.save_ledger(path, [original])
        loaded = ledger.load_ledger(path)[0]
        assert loaded == original

    def test_bad_header_rejected(self, tmp_path):
        path = tmp_path / "bad.csv"
        path.write_text("a,b\n1,2\n", encoding="utf-8")
        with pytest.raises(ledger.LedgerError, match="is not a cashflow ledger"):
            ledger.load_ledger(path)

    def test_bad_amount_rejected(self, tmp_path):
        path = tmp_path / "ledger.csv"
        header = ",".join(ledger.LEDGER_HEADERS)
        path.write_text(f"{header}\nabc,2026-10-01,not-a-number,desc,,,,\n", encoding="utf-8")
        with pytest.raises(ledger.LedgerError, match="bad amount"):
            ledger.load_ledger(path)

    def test_bad_date_rejected(self, tmp_path):
        path = tmp_path / "ledger.csv"
        header = ",".join(ledger.LEDGER_HEADERS)
        path.write_text(f"{header}\nabc,2026-13-01,1.00,desc,,,,\n", encoding="utf-8")
        with pytest.raises(ledger.LedgerError, match="Date .* is not"):
            ledger.load_ledger(path)

    def test_empty_description_rejected(self, tmp_path):
        path = tmp_path / "ledger.csv"
        header = ",".join(ledger.LEDGER_HEADERS)
        path.write_text(f"{header}\nabc,2026-10-01,1.00, ,,,,,\n", encoding="utf-8")
        with pytest.raises(ledger.LedgerError, match="description is empty"):
            ledger.load_ledger(path)


class TestAppendEntry:
    def test_appends(self, tmp_path):
        path = tmp_path / "ledger.csv"
        first = ledger.append_entry(path, entry(date="2026-10-01", amount="1.00", description="one"))
        second = ledger.append_entry(path, entry(date="2026-10-02", amount="2.00", description="two"))
        assert [e.id for e in ledger.load_ledger(path)] == [first.id, second.id]

    def test_rejects_duplicate(self, tmp_path):
        path = tmp_path / "ledger.csv"
        original = entry(date="2026-10-19", amount="-6.99", description="ADOBE CC LITE MO", account="checking")
        ledger.append_entry(path, original)
        with pytest.raises(ledger.DuplicateEntryError, match="Duplicate entry"):
            ledger.append_entry(path, entry(date="2026-10-19", amount="-6.99", description="ADOBE CC LITE MO", account="checking"))
