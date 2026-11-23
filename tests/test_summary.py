import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

import summary
from crm_audit.models import Account, AccountAudit, FieldResult, Signal
from crm_audit.reports import AccountError, write_reports

FIELD = FieldResult(
    field="annual_revenue",
    crm_value=2.2e9,
    apollo_value=3.1e9,
    sec_value=3.13e9,
    winner="sec",
    proposed_value=3.13e9,
    status="conflict",
    confidence="high",
    rationale="SEC 10-K revenue $3.13B; CRM differs by 30%.",
    evidence_url="https://www.sec.gov/Archives/edgar/data/1/1/",
)


def audit_file(tmp_path: Path) -> Path:
    hubspot = AccountAudit(
        account=Account("A1", "HubSpot", "hubspot.com", 2.2e9, "MA", "Software", 8000),
        sec_status="matched",
        ticker="HUBS",
        cik="0001404655",
        fields=(
            FIELD,
            replace(FIELD, field="employees", status="ok", proposed_value=None),
            replace(FIELD, field="industry", confidence="low", proposed_value="Software"),
            replace(FIELD, field="hq_state", confidence="medium", proposed_value="MA"),
        ),
        signals=(
            Signal("legal_name", "HUBSPOT INC", "sec", None, None),
            Signal("fiscal_year_end", "December 31", "sec", None, None),
            Signal("former_name", "Old Name (until 2020-01-01)", "sec", date(2020, 1, 1), None),
            Signal("founded_year", "2006", "apollo", None, None),
            Signal("8-K 2.05", "Restructuring or layoffs", "sec", date(2026, 10, 6), "https://a"),
            Signal("8-K 5.02", "Executive change", "sec", date(2026, 11, 12), "https://b"),
        ),
    )
    error = AccountError(Account("A2", "Bad", "bad", None, None, None, None), "not a domain")
    write_reports([hubspot, error], tmp_path, {"as_of": "2026-11-23", "apollo_live_calls": 0})
    return tmp_path / "audit.json"


def test_summary_keeps_only_what_needs_attention(tmp_path: Path) -> None:
    result = summary.summarize(json.loads(audit_file(tmp_path).read_text(encoding="utf-8")))
    assert result["counts"] == {"accounts": 2, "fixes": 2, "review": 1, "events": 2, "errors": 1}
    assert [(f["field"], f["confidence"]) for f in result["fixes"]] == [
        ("annual_revenue", "high"),
        ("hq_state", "medium"),
    ]
    assert result["fixes"][0] == {
        "account_id": "A1",
        "account": "HubSpot",
        "field": "annual_revenue",
        "current": 2.2e9,
        "proposed": 3.13e9,
        "source": "sec",
        "confidence": "high",
        "rationale": "SEC 10-K revenue $3.13B; CRM differs by 30%.",
        "evidence_url": "https://www.sec.gov/Archives/edgar/data/1/1/",
    }
    assert [r["field"] for r in result["review"]] == ["industry"]
    assert [(e["kind"], e["date"]) for e in result["events"]] == [
        ("8-K 5.02", "2026-11-12"),
        ("8-K 2.05", "2026-10-06"),
    ]
    assert result["facts"] == [
        {
            "account_id": "A1",
            "account": "HubSpot",
            "sec_status": "matched",
            "ticker": "HUBS",
            "legal_name": "HUBSPOT INC",
            "fiscal_year_end": "December 31",
            "former_names": ["Old Name (until 2020-01-01)"],
            "founded_year": "2006",
        }
    ]
    assert result["errors"] == [{"account_id": "A2", "account": "Bad", "error": "not a domain"}]


def test_cli_prints_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert summary.main(["--audit", str(audit_file(tmp_path))]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["fixes"] == 2


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        '{"accounts": [{"account": {}}]}',
        '{"accounts": [{"x": 1}]}',
        '{"accounts": [{"account": {"account_id": "A1"}, "fields": [], "signals": [{}]}]}',
        '{"accounts": [{"account": {"account_id": "A1"}, "fields": [{"x": 1}], "signals": []}]}',
    ],
)
def test_malformed_audit_file_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], body: str
) -> None:
    path = tmp_path / "audit.json"
    path.write_text(body, encoding="utf-8")
    assert summary.main(["--audit", str(path)]) == 1
    assert "error:" in capsys.readouterr().err


def test_missing_audit_file_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert summary.main(["--audit", str(tmp_path / "nope.json")]) == 1
    assert "run audit.py first" in capsys.readouterr().err


def test_output_is_ascii_so_any_console_can_print_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "audit.json"
    body = {
        "accounts": [
            {
                "account": {"account_id": "A1", "name": "\u00d8rsted \u4e2d"},
                "fields": [],
                "signals": [],
            }
        ]
    }
    path.write_text(json.dumps(body), encoding="utf-8")
    assert summary.main(["--audit", str(path)]) == 0
    out = capsys.readouterr().out
    assert out.isascii()
    assert json.loads(out)["facts"][0]["account"] == "\u00d8rsted \u4e2d"


@pytest.mark.parametrize(
    "signals",
    [
        [{"kind": 5, "detail": "x", "date": None, "url": None}],
        [
            {"kind": "8-K 5.02", "detail": "x", "date": "2026-01-01", "url": None},
            {"kind": "8-K 5.02", "detail": "x", "date": 20260101, "url": None},
        ],
    ],
)
def test_malformed_signal_types_are_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], signals: list[object]
) -> None:
    path = tmp_path / "audit.json"
    body = {"accounts": [{"account": {"account_id": "A1"}, "fields": [], "signals": signals}]}
    path.write_text(json.dumps(body), encoding="utf-8")
    assert summary.main(["--audit", str(path)]) == 1
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize("bad", [{"amount": 100}, [1], True])
def test_non_scalar_field_values_are_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], bad: object
) -> None:
    field = {**FIELD.__dict__, "proposed_value": bad}
    path = tmp_path / "audit.json"
    body = {"accounts": [{"account": {"account_id": "A1"}, "fields": [field], "signals": []}]}
    path.write_text(json.dumps(body), encoding="utf-8")
    assert summary.main(["--audit", str(path)]) == 1
    assert "error:" in capsys.readouterr().err


def test_event_counts_are_precomputed(tmp_path: Path) -> None:
    result = summary.summarize(json.loads(audit_file(tmp_path).read_text(encoding="utf-8")))
    assert result["event_counts"] == [
        {
            "account_id": "A1",
            "account": "HubSpot",
            "kind": "8-K 2.05",
            "label": "Restructuring or layoffs",
            "count": 1,
            "latest": "2026-10-06",
        },
        {
            "account_id": "A1",
            "account": "HubSpot",
            "kind": "8-K 5.02",
            "label": "Executive change",
            "count": 1,
            "latest": "2026-11-12",
        },
    ]
