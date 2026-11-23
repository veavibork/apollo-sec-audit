from dataclasses import replace
from datetime import date

import pytest

from crm_audit.models import Filing, FormerName, SecCompany
from crm_audit.rules import load_rules
from crm_audit.sec import parse_company
from crm_audit.signals import fiscal_year_end, sec_signals
from support import HUBS_CIK, load_fixture

RULES = load_rules()
AS_OF = date(2026, 11, 20)


def hubspot() -> SecCompany:
    return parse_company(HUBS_CIK, load_fixture(f"sec/submissions_{HUBS_CIK}.json"))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1231", "December 31"),
        ("0630", "June 30"),
        ("0229", "February 29"),
        ("0230", None),
        ("1301", None),
        ("abc", None),
        ("123", None),
        (None, None),
    ],
)
def test_fiscal_year_end(raw: str | None, expected: str | None) -> None:
    assert fiscal_year_end(raw) == expected


def test_hubspot_signals_from_fixture() -> None:
    signals = sec_signals(hubspot(), RULES, AS_OF)
    assert [(s.kind, s.detail) for s in signals[:2]] == [
        ("legal_name", "HUBSPOT INC"),
        ("fiscal_year_end", "December 31"),
    ]
    events = [(s.kind, s.date) for s in signals if s.kind.startswith("8-K")]
    assert events == [
        ("8-K 5.02", date(2026, 11, 12)),
        ("8-K 5.02", date(2026, 10, 9)),
        ("8-K 2.05", date(2026, 10, 6)),
        ("8-K 5.02", date(2026, 8, 5)),
        ("8-K 5.02", date(2026, 6, 16)),
        ("8-K 5.02", date(2026, 4, 1)),
    ]
    assert all(s.url and s.url.startswith("https://www.sec.gov/Archives/") for s in signals[2:])


def _filing(day: date, form: str = "8-K", items: tuple[str, ...] = ("2.01",)) -> Filing:
    return Filing(form, day, "0000000000-26-000001", items, "u", "i")


def test_window_edges_and_forms() -> None:
    company = replace(
        hubspot(),
        filings=(
            _filing(AS_OF),
            _filing(date(2025, 11, 21)),
            _filing(date(2025, 11, 20)),
            _filing(date(2026, 11, 21)),
            _filing(AS_OF, form="10-Q"),
            _filing(AS_OF, items=("9.01",)),
        ),
    )
    dates = [s.date for s in sec_signals(company, RULES, AS_OF) if s.kind.startswith("8-K")]
    assert dates == [AS_OF, date(2025, 11, 21)]


def test_former_names_become_signals() -> None:
    company = replace(
        hubspot(),
        former_names=(FormerName("Facebook Inc", date(2005, 5, 6), date(2021, 10, 27)),),
    )
    former = [s for s in sec_signals(company, RULES, AS_OF) if s.kind == "former_name"]
    assert [(s.detail, s.date) for s in former] == [
        ("Facebook Inc (until 2021-10-27)", date(2021, 10, 27))
    ]


def test_former_name_equal_to_current_name_is_dropped() -> None:
    company = replace(
        hubspot(),
        former_names=(
            FormerName("HubSpot, Inc.", None, date(2026, 11, 16)),
            FormerName("HUBSPOT INC", None, date(2026, 1, 1)),
            FormerName("HubSpot Marketing", None, date(2010, 1, 1)),
        ),
    )
    former = [s.detail for s in sec_signals(company, RULES, AS_OF) if s.kind == "former_name"]
    assert former == ["HubSpot Marketing (until 2010-01-01)"]


@pytest.mark.parametrize(
    ("former", "kept"),
    [
        ("NVIDIA CORP/CA", False),
        ("DELTA AIR LINES INC /DE/", False),
        ("ACME INC/ FA", False),
        ("APPLE COMPUTER INC/ FA", True),
    ],
)
def test_edgar_state_suffix_is_not_a_rename(former: str, kept: bool) -> None:
    names = {
        "NVIDIA CORP/CA": "NVIDIA CORP",
        "DELTA AIR LINES INC /DE/": "DELTA AIR LINES, INC.",
        "ACME INC/ FA": "Acme Inc.",
        "APPLE COMPUTER INC/ FA": "Apple Inc.",
    }
    company = replace(hubspot(), name=names[former], former_names=(FormerName(former, None, None),))
    found = [s for s in sec_signals(company, RULES, AS_OF) if s.kind == "former_name"]
    assert bool(found) is kept


def test_former_names_are_deduplicated() -> None:
    company = replace(
        hubspot(),
        name="Meta Platforms, Inc.",
        former_names=(
            FormerName("FACEBOOK INC", None, date(2021, 10, 27)),
            FormerName("FACEBOOK INC /DE/", None, date(2012, 1, 1)),
        ),
    )
    former = [s.detail for s in sec_signals(company, RULES, AS_OF) if s.kind == "former_name"]
    assert former == ["FACEBOOK INC (until 2021-10-27)"]
