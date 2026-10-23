r"""Auto-categorization rules loaded from a small CSV rule file.

Rule file format (CSV, first row is the header):

    match_type,match_value,category
    contains,KDP,Book Royalties
    exact,STAPLES CREDIT,Office Supplies
    regex,^GODADDY\.COM,Website

Rules are applied top to bottom and the first match wins. ``contains`` and
``exact`` are case-insensitive; ``regex`` is anchored however you write it.
"""
from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass

RULES_HEADERS = ["match_type", "match_value", "category"]
MATCH_TYPES = ("contains", "exact", "regex")


class RulesError(Exception):
    """The rules file is missing or malformed."""


@dataclass
class Rule:
    match_type: str
    match_value: str
    category: str


def load_rules(path: str | os.PathLike) -> list[Rule]:
    """Load and validate rules from ``path``."""
    path = os.fspath(path)
    if not os.path.exists(path):
        raise RulesError(
            f"Rules file {path!r} not found. Copy sample-data/rules.csv as a"
            " starting point, or pass a different path with --rules."
        )
    rules: list[Rule] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = [h.replace("\ufeff", "").strip().lower() for h in reader.fieldnames or []]
        if [h for h in RULES_HEADERS if h not in headers]:
            raise RulesError(
                f"{path} must have the header {','.join(RULES_HEADERS)}; found {','.join(headers)}."
            )
        for lineno, row in enumerate(reader, start=2):
            match_type = (row.get("match_type") or "").strip().lower()
            match_value = (row.get("match_value") or "").strip()
            category = (row.get("category") or "").strip()
            if not match_type and not match_value and not category:
                continue
            if match_type not in MATCH_TYPES:
                raise RulesError(
                    f"{path} line {lineno}: match_type must be one of"
                    f" {', '.join(MATCH_TYPES)} (got {match_type!r})."
                )
            if not match_value:
                raise RulesError(f"{path} line {lineno}: match_value is empty.")
            if not category:
                raise RulesError(f"{path} line {lineno}: category is empty.")
            if match_type == "regex":
                try:
                    re.compile(match_value)
                except re.error as exc:
                    raise RulesError(f"{path} line {lineno}: invalid regex {match_value!r} ({exc}).") from exc
            rules.append(Rule(match_type=match_type, match_value=match_value, category=category))
    return rules


def find_category(rules: list[Rule], text: str) -> str | None:
    """Return the category of the first rule matching ``text``, else None."""
    haystack = (text or "").casefold()
    for rule in rules:
        if rule.match_type == "contains":
            hit = rule.match_value.casefold() in haystack
        elif rule.match_type == "exact":
            hit = haystack == rule.match_value.casefold()
        else:
            hit = re.search(rule.match_value, haystack) is not None
        if hit:
            return rule.category
    return None


def apply_rules(entries, rules: list[Rule]) -> int:
    """Fill in categories for entries that do not have one yet. Returns count."""
    changed = 0
    for entry in entries:
        if entry.category:
            continue
        category = find_category(rules, entry.description)
        if category:
            entry.category = category
            changed += 1
    return changed
