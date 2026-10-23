import pytest

from cashflow import rules as rules_mod
from tests.conftest import write_text


def rules_file(tmp_path, rows: str, name="rules.csv"):
    return write_text(tmp_path / name, "match_type,match_value,category\n" + rows)


class TestLoadRules:
    def test_loads_and_preserves_order(self, tmp_path):
        path = rules_file(tmp_path, "contains,KDP,Book Royalties\ncontains,STAPLES,Office Supplies\n")
        loaded = rules_mod.load_rules(path)
        assert [(r.match_type, r.match_value, r.category) for r in loaded] == [
            ("contains", "KDP", "Book Royalties"),
            ("contains", "STAPLES", "Office Supplies"),
        ]

    def test_sample_rules_file_is_valid(self):
        from pathlib import Path

        here = Path(__file__).resolve().parent.parent / "sample-data" / "rules.csv"
        loaded = rules_mod.load_rules(here)
        assert loaded
        assert all(r.match_type in rules_mod.MATCH_TYPES for r in loaded)

    def test_missing_file(self, tmp_path):
        with pytest.raises(rules_mod.RulesError, match="not found"):
            rules_mod.load_rules(tmp_path / "ghost.csv")

    def test_unknown_match_type(self, tmp_path):
        path = rules_file(tmp_path, "startswith,KDP,Books\n")
        with pytest.raises(rules_mod.RulesError, match="match_type"):
            rules_mod.load_rules(path)

    def test_empty_match_value(self, tmp_path):
        path = rules_file(tmp_path, "contains,,Books\n")
        with pytest.raises(rules_mod.RulesError, match="match_value is empty"):
            rules_mod.load_rules(path)

    def test_empty_category(self, tmp_path):
        path = rules_file(tmp_path, "contains,KDP,\n")
        with pytest.raises(rules_mod.RulesError, match="category is empty"):
            rules_mod.load_rules(path)

    def test_invalid_regex(self, tmp_path):
        path = rules_file(tmp_path, "regex,([books,Books\n")
        with pytest.raises(rules_mod.RulesError, match="invalid regex"):
            rules_mod.load_rules(path)


class TestFindCategory:
    def loaded(self, tmp_path, rows: str):
        return rules_mod.load_rules(rules_file(tmp_path, rows))

    def test_contains_case_insensitive(self, tmp_path):
        rules = self.loaded(tmp_path, "contains,kdp,Books\n")
        assert rules_mod.find_category(rules, "KDP ROYALTY PAYOUT") == "Books"
        assert rules_mod.find_category(rules, "kdp") == "Books"

    def test_exact_whole_string(self, tmp_path):
        rules = self.loaded(tmp_path, "exact,transfer,Transfers\n")
        assert rules_mod.find_category(rules, "Transfer") == "Transfers"
        assert rules_mod.find_category(rules, "ONLINE TRANSFER 4417") is None

    def test_regex(self, tmp_path):
        rules = self.loaded(tmp_path, "regex,^godaddy\\.com,Website\n")
        assert rules_mod.find_category(rules, "Godaddy.Com Domain Renewal") == "Website"
        assert rules_mod.find_category(rules, "MY GODADDY.COM PURCHASE") is None

    def test_first_match_wins(self, tmp_path):
        rules = self.loaded(tmp_path, "contains,book,Books\ncontains,book order,Orders\n")
        assert rules_mod.find_category(rules, "MY BOOK ORDER") == "Books"

    def test_no_match(self, tmp_path):
        rules = self.loaded(tmp_path, "contains,kdp,Books\n")
        assert rules_mod.find_category(rules, "groceries") is None


class TestApplyRules:
    def test_fills_only_empty(self):
        from cashflow.ledger import Entry
        from decimal import Decimal

        entry = Entry(date="2026-10-01", amount=Decimal("-6.99"), description="ADOBE CC LITE MO")
        tagged = Entry(date="2026-10-02", amount=Decimal("1.00"), description="KDP ROYALTY", category="Already")
        rules = [rules_mod.Rule("contains", "adobe", "Software"), rules_mod.Rule("contains", "kdp", "Books")]
        changed = rules_mod.apply_rules([entry, tagged], rules)
        assert changed == 1
        assert entry.category == "Software"
        assert tagged.category == "Already"
