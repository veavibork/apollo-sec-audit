import csv
import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from crm_audit.models import Account, AccountAudit, FieldResult, Signal
from crm_audit.reports import AccountError, cell, is_fix, needs_review, uncell, write_reports

ACCOUNT = Account("A1", '=HYPERLINK("x")', "x.com", 100.0, "MA", None, 10)


def result(**overrides: Any) -> FieldResult:
    base = FieldResult(
        field="annual_revenue",
        crm_value=100.0,
        apollo_value=None,
        sec_value=200.0,
        winner="sec",
        proposed_value=200.0,
        status="conflict",
        confidence="high",
        rationale="SEC 10-K revenue; CRM differs by 50%.",
        evidence_url="https://www.sec.gov/Archives/edgar/data/1/1/",
    )
    return replace(base, **overrides)


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (None, ""),
        (3_131_266_000.0, "3131266000"),
        (2.5, "2.5"),
        (-5, "-5"),
        (date(2026, 1, 2), "2026-01-02"),
        ("=SUM(A1)", "'=SUM(A1)"),
        ("+1", "'+1"),
        ("-1", "'-1"),
        ("@cmd", "'@cmd"),
        ("\tx", "'\tx"),
        ("HubSpot", "HubSpot"),
    ],
)
def test_cell_neutralizes_formulas(value: object, text: str) -> None:
    assert cell(value) == text


@pytest.mark.parametrize("text", ["=SUM(A1)", "-1", "HubSpot", "'quoted"])
def test_uncell_round_trips(text: str) -> None:
    assert uncell(cell(text)) == text


def test_fix_and_review_rules() -> None:
    assert is_fix(result())
    assert is_fix(result(status="missing", confidence="medium"))
    assert not is_fix(result(confidence="low"))
    assert not is_fix(result(status="ok", proposed_value=None))
    assert not is_fix(result(field="domain"))
    assert needs_review(result(confidence="low"))
    assert needs_review(result(field="sec_match", confidence="low", proposed_value=None))
    assert not needs_review(result(confidence="low", status="ok"))


def test_write_reports(tmp_path: Path) -> None:
    audit = AccountAudit(
        account=ACCOUNT,
        sec_status="matched",
        ticker="X",
        cik="0000000001",
        fields=(
            result(),
            result(field="industry", confidence="low", proposed_value="Software"),
            result(field="employees", status="ok", proposed_value=None, confidence="medium"),
        ),
        signals=(Signal("8-K 5.02", "Executive change", "sec", date(2026, 10, 9), "https://u"),),
    )
    error = AccountError(Account("A2", "Y", "bad", None, None, None, None), "not a domain")
    counts = write_reports([audit, error], tmp_path, {"as_of": "2026-11-20"})
    assert counts == {"accounts": 2, "errors": 1, "fixes": 1, "review": 1, "signals": 1}

    with (tmp_path / "proposed_fixes.csv").open(encoding="utf-8", newline="") as f:
        fixes = list(csv.DictReader(f))
    assert fixes[0]["proposed_value"] == "200"
    assert fixes[0]["approved"] == ""
    with (tmp_path / "needs_review.csv").open(encoding="utf-8", newline="") as f:
        assert [r["field"] for r in csv.DictReader(f)] == ["industry"]
    with (tmp_path / "signals.csv").open(encoding="utf-8", newline="") as f:
        (signal,) = csv.DictReader(f)
    assert signal["account_name"] == '\'=HYPERLINK("x")'
    assert signal["date"] == "2026-10-09"

    data = json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))
    assert data["as_of"] == "2026-11-20"
    assert data["accounts"][0]["signals"][0]["date"] == "2026-10-09"
    assert data["accounts"][1] == {"error": "not a domain", "account": error.account.__dict__}


@pytest.mark.parametrize("text", ["'=x", "''", "'-Other"])
def test_leading_apostrophe_round_trips(text: str) -> None:
    assert cell(text).startswith("''")
    assert uncell(cell(text)) == text
