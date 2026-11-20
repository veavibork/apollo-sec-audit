import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"

APOLLO_ALLOWED_KEYS = {
    "name",
    "primary_domain",
    "website_url",
    "publicly_traded_symbol",
    "publicly_traded_exchange",
    "city",
    "state",
    "country",
    "id",
    "annual_revenue",
    "annual_revenue_printed",
    "estimated_num_employees",
    "founded_year",
    "industry",
    "sic_codes",
    "naics_codes",
    "keywords",
    "current_technologies",
    "suborganizations",
    "short_description",
}


def load(rel: str) -> Any:
    return json.loads((FIXTURES / rel).read_text(encoding="utf-8"))


def test_apollo_fixture_holds_only_approved_fields() -> None:
    org = load("apollo/hubspot.com.json")["organization"]
    assert set(org) <= APOLLO_ALLOWED_KEYS


def test_apollo_fixture_marks_itself_as_fake() -> None:
    org = load("apollo/hubspot.com.json")["organization"]
    assert "fake" in org["short_description"].lower()


def test_submissions_recent_arrays_are_parallel() -> None:
    recent = load("sec/submissions_0001404655.json")["filings"]["recent"]
    assert len({len(v) for v in recent.values()}) == 1
