"""Regression harness: hand-written cases in tests/golden/cases.json with expected outcomes."""

import json
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from crm_audit.compare import compare_account, money
from crm_audit.matching import find_sec
from crm_audit.models import (
    Account,
    AccountAudit,
    ApolloOrg,
    FieldResult,
    FormerName,
    SecCompany,
    SecRevenue,
    TickerMatch,
)
from crm_audit.rules import load_industries, load_rules
from crm_audit.sec import REVENUE_CONCEPTS

GOLDEN = json.loads((Path(__file__).parent / "golden" / "cases.json").read_text(encoding="utf-8"))
AS_OF = date.fromisoformat(GOLDEN["as_of"])
RULES = load_rules()
INDUSTRIES = load_industries()
CIK = "0000000001"
ACCESSION = "0000000000-26-000001"


def merged(case: dict[str, Any], part: str) -> dict[str, Any] | None:
    if part in case and case[part] is None:
        return None
    base: dict[str, Any] = GOLDEN["defaults"][part]
    override: dict[str, Any] = case.get(part, {})
    return base | override


class FakeSec:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self.data = data

    def cik_for_ticker(self, ticker: str) -> TickerMatch | None:
        if self.data is None or not self.data["ticker_known"]:
            return None
        return TickerMatch(CIK, ticker, self.data["name"])

    def company(self, cik: str | int) -> SecCompany:
        assert self.data is not None
        return SecCompany(
            cik=CIK,
            name=self.data["name"],
            former_names=tuple(FormerName(n, None, None) for n in self.data["former_names"]),
            sic=self.data["sic"],
            sic_description=self.data["sic_description"],
            fiscal_year_end=self.data["fiscal_year_end"],
            business_state=self.data["state"],
            exchanges=(),
            filings=(),
        )

    def annual_revenue(
        self, cik: str | int, concepts: Iterable[str] = REVENUE_CONCEPTS
    ) -> SecRevenue | None:
        assert self.data is not None
        if self.data["revenue"] is None:
            return None
        end = date.fromisoformat(self.data["revenue_end"])
        return SecRevenue(
            float(self.data["revenue"]),
            "Revenues",
            end - timedelta(days=364),
            end,
            end + timedelta(days=45),
            ACCESSION,
            "https://www.sec.gov/Archives/edgar/data/1/000000000026000001/",
        )


def to_org(data: dict[str, Any] | None) -> ApolloOrg | None:
    if data is None:
        return None
    fields: dict[str, Any] = dict.fromkeys(ApolloOrg.__dataclass_fields__)
    fields |= {"sic_codes": (), "naics_codes": ()}
    return ApolloOrg(**(fields | data))


def run(case: dict[str, Any]) -> AccountAudit:
    account_data = merged(case, "account")
    assert account_data is not None
    account = Account(**account_data)
    org = to_org(merged(case, "apollo"))
    lookup = find_sec(org, account.name, FakeSec(merged(case, "sec")), RULES)
    return compare_account(account, org, lookup, RULES, INDUSTRIES, AS_OF)


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=[c["id"] for c in GOLDEN["cases"]])
def test_golden_case(case: dict[str, Any]) -> None:
    audit = run(case)
    actual = {f.field: [f.status, f.confidence, f.proposed_value] for f in audit.fields}
    assert actual == case["expect"]
    assert audit.sec_status == case.get("sec_status", "matched")
    if "signals" in case:
        assert [s.kind for s in audit.signals] == case["signals"]


def test_golden_case_ids_are_unique() -> None:
    ids = [c["id"] for c in GOLDEN["cases"]]
    assert len(ids) == len(set(ids))


def case(case_id: str) -> dict[str, Any]:
    return next(c for c in GOLDEN["cases"] if c["id"] == case_id)


def field(audit: AccountAudit, name: str) -> FieldResult:
    return next(f for f in audit.fields if f.field == name)


def test_revenue_rationale_names_source_rule_and_differences() -> None:
    audit = run(case("stale_revenue"))
    revenue = field(audit, "annual_revenue")
    assert revenue.rationale == (
        "SEC 10-K revenue $3.13B for the year ending 2025-12-31; "
        "CRM differs by 30%; Apollo differs by 0%."
    )
    assert revenue.evidence_url is not None
    assert revenue.evidence_url.startswith("https://www.sec.gov/Archives/")
    assert (revenue.winner, revenue.sec_value, revenue.apollo_value) == (
        "sec",
        3131266000,
        3131244000,
    )
    assert (audit.ticker, audit.cik) == ("HUBS", CIK)


def test_low_confidence_rationale_explains_the_cap() -> None:
    revenue = field(run(case("sec_name_check_borderline")), "annual_revenue")
    assert "name check borderline (82.4)" in revenue.rationale
    review = field(run(case("sec_name_check_borderline")), "sec_match")
    assert review.rationale.startswith("Ticker HUBS maps to SEC 'NORTHWIND TRADING CO'")
    assert review.rationale.endswith("SEC data used at low confidence.")


def test_failed_sec_match_says_sec_not_used() -> None:
    review = field(run(case("sec_name_check_fails")), "sec_match")
    assert review.rationale.endswith("SEC data not used.")


def test_wrong_domain_review_points_at_domain() -> None:
    review = field(run(case("crm_domain_points_to_other_company")), "domain")
    assert review.crm_value == "hubspot.com"
    assert "may belong to a different company" in review.rationale


def test_industry_shows_apollo_label_for_display_only() -> None:
    industry = field(run(case("private_company")), "industry")
    assert (industry.apollo_value, industry.winner, industry.status) == (
        "computer software",
        None,
        "unverified",
    )


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (3_131_266_000, "$3.13B"),
        (40_000_000, "$40.00M"),
        (12_500, "$12.50K"),
        (999, "$999"),
        (999_999, "$1.00M"),
        (999_999_999, "$1.00B"),
        (999.99, "$1.00K"),
    ],
)
def test_money(value: float, text: str) -> None:
    assert money(value) == text
