from typing import Any

import pytest

from crm_audit.cache import JsonCache
from crm_audit.matching import check_name, find_sec, normalize_name
from crm_audit.models import ApolloOrg
from crm_audit.rules import load_rules
from crm_audit.sec import SecClient
from support import HUBS_CIK, USER_AGENT, load_fixture

RULES = load_rules()
STRIP = RULES.name_match.strip_words


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HubSpot, Inc.", "hubspot"),
        ("AT&T INC.", "at and t"),
        ("Coca-Cola Co", "coca cola"),
        ("The Company", "the company"),
        ("Nestlé S.A.", "nestlé s a"),
    ],
)
def test_normalize_name(raw: str, expected: str) -> None:
    assert normalize_name(raw, STRIP) == expected


@pytest.mark.parametrize(
    ("name", "candidates", "verdict", "compared_to"),
    [
        ("HubSpot", ["HUBSPOT INC"], "pass", "HUBSPOT INC"),
        ("Google", ["Alphabet Inc.", "Google Inc."], "pass", "Google Inc."),
        ("Northwind Traders", ["NORTHWIND TRADING CO"], "borderline", "NORTHWIND TRADING CO"),
        ("Acme Robotics", ["ZEBRA FOODS INC"], "fail", "ZEBRA FOODS INC"),
        ("", ["HUBSPOT INC"], "fail", "HUBSPOT INC"),
    ],
)
def test_check_name(name: str, candidates: list[str], verdict: str, compared_to: str) -> None:
    check = check_name(name, candidates, RULES.name_match)
    assert (check.verdict, check.compared_to) == (verdict, compared_to)


def test_check_name_with_no_candidates_fails() -> None:
    assert check_name("HubSpot", [], RULES.name_match).verdict == "fail"


def make_org(**overrides: Any) -> ApolloOrg:
    base: dict[str, Any] = {
        "name": "HubSpot",
        "domain": "hubspot.com",
        "annual_revenue": None,
        "estimated_num_employees": None,
        "founded_year": None,
        "publicly_traded_symbol": "HUBS",
        "publicly_traded_exchange": None,
        "city": None,
        "state": None,
        "country": None,
        "industry": None,
        "sic_codes": (),
        "naics_codes": (),
        "total_funding": None,
        "latest_funding_stage": None,
    }
    return ApolloOrg(**(base | overrides))


@pytest.fixture
def sec(cache: JsonCache) -> SecClient:
    for name in (
        "company_tickers.json",
        f"submissions_{HUBS_CIK}.json",
        f"companyfacts_{HUBS_CIK}.json",
    ):
        cache.put(f"sec/{name}", load_fixture(f"sec/{name}"))
    return SecClient(cache, USER_AGENT)


def test_find_sec_matches_by_ticker(sec: SecClient) -> None:
    lookup = find_sec(make_org(), "HubSpot", sec, RULES)
    assert lookup.status == "matched"
    assert lookup.match is not None and lookup.match.cik == HUBS_CIK
    assert lookup.company is not None and lookup.company.name == "HUBSPOT INC"
    assert lookup.revenue is not None and lookup.revenue.value == 3_131_266_000
    assert lookup.name_check is not None and lookup.name_check.verdict == "pass"


def test_find_sec_falls_back_to_crm_name(sec: SecClient) -> None:
    lookup = find_sec(make_org(name=None), "HubSpot Inc", sec, RULES)
    assert lookup.name_check is not None and lookup.name_check.verdict == "pass"


def test_find_sec_without_org_ticker_or_sec_row(sec: SecClient) -> None:
    assert find_sec(None, "x", sec, RULES).status == "no_apollo_org"
    assert find_sec(make_org(publicly_traded_symbol=None), "x", sec, RULES).status == "no_ticker"
    missing = find_sec(make_org(publicly_traded_symbol="ZZZZ"), "x", sec, RULES)
    assert (missing.status, missing.ticker) == ("ticker_not_in_sec", "ZZZZ")
