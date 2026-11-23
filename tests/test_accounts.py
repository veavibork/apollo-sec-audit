from pathlib import Path

import pytest

from crm_audit.accounts import load_accounts

HEADER = "account_id,name,domain,annual_revenue,hq_state,industry,employees\n"


def write(tmp_path: Path, body: str, header: str = HEADER) -> Path:
    path = tmp_path / "accounts.csv"
    path.write_text(header + body, encoding="utf-8")
    return path


def test_loads_and_blanks_become_none(tmp_path: Path) -> None:
    path = write(tmp_path, "A1,HubSpot,hubspot.com,3100000000,MA,Software,8000\nA2,Stripe,,,,,\n")
    first, second = load_accounts(path)
    assert first.annual_revenue == 3_100_000_000.0
    assert first.employees == 8000
    assert (second.domain, second.annual_revenue, second.employees) == (None, None, None)


def test_column_order_may_differ(tmp_path: Path) -> None:
    header = "name,account_id,domain,employees,annual_revenue,hq_state,industry\n"
    (account,) = load_accounts(
        write(tmp_path, "HubSpot,A1,hubspot.com,8000,1,MA,Software\n", header)
    )
    assert account.account_id == "A1"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("A1,X,x.com,lots,MA,Software,1\n", "line 2: annual_revenue 'lots' is not a number"),
        ("A1,X,x.com,-5,MA,Software,1\n", "must be a non-negative number"),
        ("A1,X,x.com,nan,MA,Software,1\n", "must be a non-negative number"),
        ("A1,X,x.com,1,MA,Software,12.5\n", "employees '12.5' must be a whole number"),
        (",X,x.com,1,MA,Software,1\n", "account_id is blank"),
        ("A1,X,x.com,1,MA,S,1\nA1,Y,y.com,1,MA,S,1\n", "line 3: duplicate account_id A1"),
    ],
)
def test_bad_rows_name_the_line(tmp_path: Path, body: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_accounts(write(tmp_path, body))


def test_wrong_columns_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="columns must be"):
        load_accounts(write(tmp_path, "A1,X\n", "account_id,name\n"))
