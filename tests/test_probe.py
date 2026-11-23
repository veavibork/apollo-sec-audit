import shutil
from pathlib import Path

import pytest

import probe
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
    with pytest.raises(SystemExit, match="APOLLO_API_KEY is not set"):
        probe.main(["--domain", "hubspot.com"], root=tmp_path)
