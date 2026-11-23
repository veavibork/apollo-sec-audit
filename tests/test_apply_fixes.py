import csv
from pathlib import Path

import pytest

import apply_fixes
from crm_audit.reports import FIX_COLUMNS, cell

ACCOUNTS = (
    "account_id,name,domain,annual_revenue,hq_state,industry,employees\n"
    "A1,HubSpot,hubspot.com,2200000000,CA,,8000\n"
    "A2,=Evil,evil.com,10,TX,Software,5\n"
)
FIX_HEADER = ",".join((*FIX_COLUMNS, "approved")) + "\n"


def setup(tmp_path: Path, fixes: str) -> tuple[Path, Path, Path]:
    accounts, fix_file, out = tmp_path / "a.csv", tmp_path / "f.csv", tmp_path / "out.csv"
    accounts.write_text(ACCOUNTS, encoding="utf-8")
    fix_file.write_text(FIX_HEADER + fixes, encoding="utf-8")
    return accounts, fix_file, out


def run(accounts: Path, fixes: Path, out: Path) -> int:
    return apply_fixes.main(["--accounts", str(accounts), "--fixes", str(fixes), "--out", str(out)])


def rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return {r["account_id"]: r for r in csv.DictReader(f)}


def test_applies_only_approved_rows(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    accounts, fixes, out = setup(
        tmp_path,
        "A1,annual_revenue,2200000000,3131266000,sec,u,high,r,y\n"
        "A1,hq_state,CA,MA,sec,u,high,r,n\n"
        "A1,industry,,Software,sec,u,high,r,YES\n"
        "A1,employees,8000,8500,apollo,,medium,r,\n",
    )
    assert run(accounts, fixes, out) == 0
    updated = rows(out)["A1"]
    assert updated["annual_revenue"] == "3131266000"
    assert updated["hq_state"] == "CA"
    assert updated["industry"] == "Software"
    assert updated["employees"] == "8000"
    assert accounts.read_text(encoding="utf-8") == ACCOUNTS
    output = capsys.readouterr().out
    assert "2 applied, 0 skipped" in output
    assert "annual_revenue: 2200000000 -> 3131266000" in output
    assert "industry: (blank) -> Software" in output


@pytest.mark.parametrize(
    ("fix", "reason"),
    [
        ("A1,annual_revenue,1000,3131266000,sec,u,high,r,y\n", "CRM value changed since the audit"),
        ("A9,annual_revenue,1,2,sec,u,high,r,y\n", "account not in the accounts file"),
        ("A1,name,HubSpot,HUBSPOT INC,sec,u,high,r,y\n", "can't be edited"),
        ("A1,hq_state,CA,Massachusetts,sec,u,high,r,y\n", "not a two-letter US state code"),
        ("A1,industry,,Restaurants | Software,apollo,,low,r,y\n", "lists several labels"),
        ("A1,industry,,=HYPERLINK(1),sec,u,high,r,y\n", "not a known industry label"),
        ("A1,industry,,Widgets,sec,u,high,r,y\n", "not a known industry label"),
        ("A1,employees,8000,lots,apollo,,medium,r,y\n", "must be a whole number"),
        ("A1,annual_revenue,2200000000,,sec,u,high,r,y\n", "proposed value is blank"),
    ],
)
def test_skips_unsafe_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fix: str, reason: str
) -> None:
    accounts, fixes, out = setup(tmp_path, fix)
    assert run(accounts, fixes, out) == 0
    output = capsys.readouterr().out
    assert "0 applied, 1 skipped" in output
    assert reason in output
    assert rows(out) == rows(accounts)


def test_second_approval_for_same_field_is_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    accounts, fixes, out = setup(
        tmp_path,
        "A1,hq_state,CA,MA,sec,u,high,r,y\nA1,hq_state,CA,NY,apollo,,medium,r,y\n",
    )
    run(accounts, fixes, out)
    assert rows(out)["A1"]["hq_state"] == "MA"
    assert "already changed by an earlier approved row" in capsys.readouterr().out


def test_formula_escaped_current_value_still_matches(tmp_path: Path) -> None:
    accounts, fixes, out = setup(tmp_path, "A2,industry,Software,Retail,sec,u,high,r,y\n")
    run(accounts, fixes, out)
    assert rows(out)["A2"]["industry"] == "Retail"
    assert rows(out)["A2"]["name"] == "=Evil"


def test_refuses_to_overwrite_input(tmp_path: Path) -> None:
    accounts, fixes, _ = setup(tmp_path, "")
    assert run(accounts, fixes, accounts) == 1
    assert accounts.read_text(encoding="utf-8") == ACCOUNTS


def test_rejects_fix_file_with_wrong_columns(tmp_path: Path) -> None:
    accounts, fixes, out = setup(tmp_path, "")
    fixes.write_text("account_id,field\n", encoding="utf-8")
    assert run(accounts, fixes, out) == 1


def test_short_rows_do_not_crash(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    accounts, fixes, out = setup(tmp_path, "A1,annual_revenue,2200000000,3131266000,sec,u,high,r\n")
    assert run(accounts, fixes, out) == 0
    assert "0 applied, 0 skipped" in capsys.readouterr().out


@pytest.mark.parametrize(
    "extra_row",
    ["A3,Acme,acme.com,1,TX,Software,10,extra\n", "A1,Dup,dup.com,1,TX,Software,10\n"],
)
def test_bad_accounts_file_writes_nothing(tmp_path: Path, extra_row: str) -> None:
    accounts, fixes, out = setup(tmp_path, "A1,hq_state,CA,MA,sec,u,high,r,y\n")
    accounts.write_text(ACCOUNTS + extra_row, encoding="utf-8")
    assert run(accounts, fixes, out) == 1
    assert not out.exists()


def test_formula_prefixed_account_id_is_decoded(tmp_path: Path) -> None:
    accounts, fixes, out = setup(tmp_path, "")
    accounts.write_text(ACCOUNTS + "=A3,Acme,acme.com,1,TX,Software,10\n", encoding="utf-8")
    fixes.write_text(
        FIX_HEADER + f"{cell('=A3')},hq_state,TX,CA,sec,u,high,r,y\n", encoding="utf-8"
    )
    assert run(accounts, fixes, out) == 0
    assert rows(out)["=A3"]["hq_state"] == "CA"


def test_formula_prefixed_current_value_round_trips(tmp_path: Path) -> None:
    accounts, fixes, out = setup(tmp_path, "")
    accounts.write_text(ACCOUNTS.replace("TX,Software,5", "TX,-Other,5"), encoding="utf-8")
    fixes.write_text(
        FIX_HEADER + f"A2,industry,{cell('-Other')},Software,sec,u,high,r,y\n", encoding="utf-8"
    )
    assert run(accounts, fixes, out) == 0
    assert rows(out)["A2"]["industry"] == "Software"


def test_write_atomic_failure_keeps_destination(tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    out.write_text("original\n", encoding="utf-8")
    bad_rows = [{"a": "1"}, {"a": "2", "extra": "x"}]
    with pytest.raises(ValueError):
        apply_fixes.write_atomic(out, ["a"], bad_rows)
    assert out.read_text(encoding="utf-8") == "original\n"
    assert [p.name for p in tmp_path.iterdir()] == ["out.csv"]


def run_approve(accounts: Path, fixes: Path, out: Path, *pairs: str) -> int:
    argv = ["--accounts", str(accounts), "--fixes", str(fixes), "--out", str(out)]
    for pair in pairs:
        argv += ["--approve", pair]
    return apply_fixes.main(argv)


def test_approve_flag_records_and_applies(tmp_path: Path) -> None:
    accounts, fixes, out = setup(
        tmp_path,
        "A1,annual_revenue,2200000000,3131266000,sec,u,high,r,\nA1,hq_state,CA,MA,sec,u,high,r,\n",
    )
    assert run_approve(accounts, fixes, out, "A1:annual_revenue") == 0
    assert rows(out)["A1"]["annual_revenue"] == "3131266000"
    assert rows(out)["A1"]["hq_state"] == "CA"
    with fixes.open(encoding="utf-8", newline="") as f:
        recorded = {(r["account_id"], r["field"]): r["approved"] for r in csv.DictReader(f)}
    assert recorded == {("A1", "annual_revenue"): "y", ("A1", "hq_state"): ""}


@pytest.mark.parametrize("pair", ["A1:employees", "A9:hq_state", "nonsense"])
def test_approve_flag_rejects_unknown_pairs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], pair: str
) -> None:
    accounts, fixes, out = setup(tmp_path, "A1,hq_state,CA,MA,sec,u,high,r,\n")
    before = fixes.read_text(encoding="utf-8")
    assert run_approve(accounts, fixes, out, pair) == 1
    assert "--approve" in capsys.readouterr().err
    assert fixes.read_text(encoding="utf-8") == before
    assert not out.exists()


def test_existing_output_is_not_overwritten_without_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    accounts, fixes, out = setup(tmp_path, "A1,hq_state,CA,MA,sec,u,high,r,y\n")
    out.write_text("earlier round\n", encoding="utf-8")
    assert run(accounts, fixes, out) == 1
    assert "already exists" in capsys.readouterr().err
    assert out.read_text(encoding="utf-8") == "earlier round\n"
    argv = ["--accounts", str(accounts), "--fixes", str(fixes), "--out", str(out), "--force"]
    assert apply_fixes.main(argv) == 0
    assert rows(out)["A1"]["hq_state"] == "MA"


def test_failed_output_write_records_no_approvals(tmp_path: Path) -> None:
    accounts, fixes, _ = setup(tmp_path, "A1,hq_state,CA,MA,sec,u,high,r,\n")
    before = fixes.read_text(encoding="utf-8")
    out = tmp_path / "missing-dir" / "out.csv"
    assert run_approve(accounts, fixes, out, "A1:hq_state") == 1
    assert fixes.read_text(encoding="utf-8") == before


def test_whitespace_prefixed_account_id_matches(tmp_path: Path) -> None:
    accounts, fixes, out = setup(tmp_path, "")
    accounts.write_text(ACCOUNTS + "\tA5,Acme,acme.com,1,TX,Software,10\n", encoding="utf-8")
    fixes.write_text(
        FIX_HEADER + f"{cell(chr(9) + 'A5')},hq_state,TX,CA,sec,u,high,r,\n", encoding="utf-8"
    )
    assert run_approve(accounts, fixes, out, "A5:hq_state") == 0
    assert rows(out)["\tA5"]["hq_state"] == "CA"


def test_approve_splits_on_last_colon(tmp_path: Path) -> None:
    accounts, fixes, out = setup(tmp_path, "")
    accounts.write_text(ACCOUNTS + "ACME:001,Acme,acme.com,1,TX,Software,10\n", encoding="utf-8")
    fixes.write_text(FIX_HEADER + "ACME:001,hq_state,TX,CA,sec,u,high,r,\n", encoding="utf-8")
    assert run_approve(accounts, fixes, out, "ACME:001:hq_state") == 0
    assert rows(out)["ACME:001"]["hq_state"] == "CA"


def test_approve_does_not_override_a_reviewers_no(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    accounts, fixes, out = setup(tmp_path, "A1,hq_state,CA,MA,sec,u,high,r,n\n")
    before = fixes.read_text(encoding="utf-8")
    assert run_approve(accounts, fixes, out, "A1:hq_state") == 1
    assert "already marked 'n'" in capsys.readouterr().err
    assert fixes.read_text(encoding="utf-8") == before


def test_output_shows_decoded_account_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    accounts, fixes, out = setup(tmp_path, "")
    accounts.write_text(ACCOUNTS + "=A3,Acme,acme.com,1,TX,Software,10\n", encoding="utf-8")
    fixes.write_text(
        FIX_HEADER + f"{cell('=A3')},hq_state,TX,CA,sec,u,high,r,y\n", encoding="utf-8"
    )
    run(accounts, fixes, out)
    assert "line 2 =A3 applied" in capsys.readouterr().out


def test_fixes_row_with_extra_values_is_rejected_before_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    accounts, fixes, out = setup(tmp_path, "A1,hq_state,CA,MA,sec,u,high,r,,surprise\n")
    before = fixes.read_text(encoding="utf-8")
    assert run_approve(accounts, fixes, out, "A1:hq_state") == 1
    assert "line 2: more values than columns" in capsys.readouterr().err
    assert not out.exists()
    assert fixes.read_text(encoding="utf-8") == before
