import shutil
from pathlib import Path

import pytest
import responses

import probe
from crm_audit.apollo import ENRICH_URL
from support import FIXTURES, USER_AGENT


def seed_cache(root: Path) -> None:
    shutil.copytree(FIXTURES / "apollo", root / "cache" / "apollo")
    shutil.copytree(FIXTURES / "sec", root / "cache" / "sec")


def test_probe_runs_from_cache_without_apollo_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seed_cache(tmp_path)
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)
    monkeypatch.setenv("SEC_USER_AGENT", USER_AGENT)
    probe.main(["--domain", "hubspot.com"], root=tmp_path)
    out = capsys.readouterr().out
    assert "HUBS -> CIK 0001404655" in out
    assert "3131266000" in out


def test_probe_exits_cleanly_when_uncached_and_no_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)
    monkeypatch.setenv("SEC_USER_AGENT", USER_AGENT)
    with pytest.raises(SystemExit, match="APOLLO_API_KEY is not set"):
        probe.main(["--domain", "hubspot.com"], root=tmp_path)


def test_probe_checks_sec_config_before_spending_a_credit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APOLLO_API_KEY", "test-key-not-real")
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(SystemExit, match="SEC_USER_AGENT"):
        probe.main(["--domain", "hubspot.com"], root=tmp_path)


def test_probe_reports_credits_spent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seed_cache(tmp_path)
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)
    monkeypatch.setenv("SEC_USER_AGENT", USER_AGENT)
    probe.main(["--domain", "hubspot.com"], root=tmp_path)
    assert "Apollo live calls: 0" in capsys.readouterr().out


@responses.activate
def test_probe_reports_live_calls_when_enrich_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    responses.get(ENRICH_URL, status=500)
    monkeypatch.setenv("APOLLO_API_KEY", "test-key-not-real")
    monkeypatch.setenv("SEC_USER_AGENT", USER_AGENT)
    with pytest.raises(SystemExit, match="HTTP 500"):
        probe.main(["--domain", "hubspot.com"], root=tmp_path)
    assert "Apollo live calls: 1" in capsys.readouterr().out
