from __future__ import annotations

from pathlib import Path

import pytest

from cashflow import ledger as ledger_mod

SAMPLE_DATA = Path(__file__).resolve().parent.parent / "sample-data"


@pytest.fixture
def tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def entry(date="2026-10-01", amount="1.00", description="Sample", **kwargs):
    return ledger_mod.Entry(date=date, amount=ledger_mod.parse_amount(amount), description=description, **kwargs)


def write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path
