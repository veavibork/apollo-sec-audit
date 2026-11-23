import csv
import json
import shutil
from pathlib import Path

import pytest
import responses

import audit
from crm_audit.apollo import ENRICH_URL
from support import FIXTURES, USER_AGENT

HEADER = "account_id,name,domain,annual_revenue,hq_state,industry,employees\n"
AS_OF = "2026-11-20"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copytree(FIXTURES / "apollo", tmp_path / "cache" / "apollo")
    shutil.copytree(FIXTURES / "sec", tmp_path / "cache" / "sec")
    (tmp_path / "accounts.csv").write_text(
        HEADER
        + "A1,HubSpot,hubspot.com,2200000000,MA,Software,8000\n"
        + "A2,Example Co,example.com,1000,TX,Software,10\n"
        + "A3,Bad Domain,not a domain,,,,\n"
        + "A4,No Domain,,,,,\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SEC_USER_AGENT", USER_AGENT)
    monkeypatch.setenv("APOLLO_API_KEY", "test-key-not-real")
    monkeypatch.delenv("APOLLO_MAX_LIVE_CALLS", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(*extra: str) -> int:
    return audit.main(
        ["--accounts", "accounts.csv", "--out", "reports", "--cache", "cache", "--as-of", AS_OF]
        + list(extra)
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@responses.activate
def test_dry_run_makes_no_apollo_calls(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run() == 0
    out = capsys.readouterr().out
    assert "1 domains not in the Apollo cache" in out
    assert "Apollo live calls this run: 0" in out
    assert "A2: example.com is not cached; rerun with --live" in out
    assert "A3: not a domain" in out
    assert len(responses.calls) == 0

    fixes = read_csv(workspace / "reports" / "proposed_fixes.csv")
    assert [(f["account_id"], f["field"], f["proposed_value"]) for f in fixes] == [
        ("A1", "annual_revenue", "3131266000")
    ]
    data = json.loads((workspace / "reports" / "audit.json").read_text(encoding="utf-8"))
    assert [a.get("sec_status") for a in data["accounts"]] == [
        "matched",
        None,
        None,
        "no_apollo_org",
    ]
    signals = read_csv(workspace / "reports" / "signals.csv")
    assert {s["kind"] for s in signals} >= {"legal_name", "fiscal_year_end", "8-K 5.02"}


@responses.activate
def test_live_run_fetches_uncached_domains(workspace: Path) -> None:
    responses.get(ENRICH_URL, json={"organization": None})
    assert run("--live") == 0
    assert len(responses.calls) == 1
    assert (workspace / "cache" / "apollo" / "example.com.json").exists()


@responses.activate
def test_live_call_cap_stops_without_reports(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("--live", "--max-live-calls", "0") == 2
    assert "live call limit (0) reached" in capsys.readouterr().err
    assert not (workspace / "reports").exists()
    assert len(responses.calls) == 0


def test_cap_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APOLLO_MAX_LIVE_CALLS", "3")
    assert audit.max_live_calls(None) == 3
    monkeypatch.setenv("APOLLO_MAX_LIVE_CALLS", "lots")
    with pytest.raises(ValueError):
        audit.max_live_calls(None)
    assert audit.max_live_calls(5) == 5


def test_missing_user_agent_fails_fast(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "")
    assert run() == 1
    assert "SEC_USER_AGENT" in capsys.readouterr().err


@responses.activate
def test_corrupt_apollo_cache_fails_only_that_account(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (workspace / "cache" / "apollo" / "example.com.json").write_text("{bad", encoding="utf-8")
    assert run() == 0
    assert "A2: corrupt cache file" in capsys.readouterr().out


@responses.activate
def test_live_without_key_fails_before_any_work(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("APOLLO_API_KEY", "")
    assert run("--live") == 1
    assert "APOLLO_API_KEY" in capsys.readouterr().err
    assert not (workspace / "reports").exists()


def test_negative_cap_is_an_error(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run("--live", "--max-live-calls", "-1") == 1
    assert "max-live-calls" in capsys.readouterr().err


@responses.activate
def test_rerun_keeps_approvals_unless_forced(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run() == 0
    fixes_path = workspace / "reports" / "proposed_fixes.csv"
    rows = read_csv(fixes_path)
    rows[0]["approved"] = "y"
    with fixes_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    approved = fixes_path.read_text(encoding="utf-8")

    assert run("--live") == 1
    assert "has approvals" in capsys.readouterr().err
    assert fixes_path.read_text(encoding="utf-8") == approved
    assert len(responses.calls) == 0

    assert run("--force") == 0
    assert read_csv(fixes_path)[0]["approved"] == ""
