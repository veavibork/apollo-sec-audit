from typing import Any

import pytest
import responses
from responses import matchers

from crm_audit.apollo import ENRICH_URL, ApolloClient, normalize_domain, trim
from crm_audit.cache import JsonCache
from crm_audit.errors import LiveCallLimitReached, SourceError
from support import load_fixture

KEY = "test-key-not-real"


def client(cache: JsonCache, key: str | None = KEY, max_live_calls: int = 5) -> ApolloClient:
    return ApolloClient(cache, key, max_live_calls)


def hubspot() -> Any:
    return load_fixture("apollo/hubspot.com.json")


@responses.activate
def test_cache_miss_makes_one_call_and_writes_cache(cache: JsonCache) -> None:
    responses.get(
        ENRICH_URL,
        json=hubspot(),
        match=[
            matchers.query_param_matcher({"domain": "hubspot.com"}),
            matchers.header_matcher({"x-api-key": KEY}),
        ],
    )
    apollo = client(cache)
    org = apollo.enrich("hubspot.com")
    assert org is not None and org.name == "HubSpot"
    assert len(responses.calls) == 1
    assert apollo.live_calls == 1
    assert cache.get("apollo/hubspot.com.json") == hubspot()


@responses.activate
def test_cache_hit_without_key_makes_no_call(cache: JsonCache) -> None:
    cache.put("apollo/hubspot.com.json", hubspot())
    apollo = client(cache, key=None)
    org = apollo.enrich("hubspot.com")
    assert org is not None and org.domain == "hubspot.com"
    assert len(responses.calls) == 0
    assert apollo.live_calls == 0


@responses.activate
def test_http_error_raises_and_writes_no_cache(cache: JsonCache) -> None:
    responses.get(ENRICH_URL, status=500)
    with pytest.raises(SourceError, match="HTTP 500"):
        client(cache).enrich("hubspot.com")
    assert cache.get("apollo/hubspot.com.json") is None


@responses.activate
def test_invalid_json_raises_and_writes_no_cache(cache: JsonCache) -> None:
    responses.get(ENRICH_URL, body="not json", status=200)
    with pytest.raises(SourceError, match="not valid JSON"):
        client(cache).enrich("hubspot.com")
    assert cache.get("apollo/hubspot.com.json") is None


@responses.activate
def test_non_object_json_raises_and_writes_no_cache(cache: JsonCache) -> None:
    responses.get(ENRICH_URL, json=["unexpected"])
    with pytest.raises(SourceError, match="not a JSON object"):
        client(cache).enrich("hubspot.com")
    assert cache.get("apollo/hubspot.com.json") is None


@responses.activate
def test_missing_key_on_cache_miss_raises_without_calling(cache: JsonCache) -> None:
    with pytest.raises(SourceError, match="APOLLO_API_KEY is not set"):
        client(cache, key=None).enrich("hubspot.com")
    assert len(responses.calls) == 0


@responses.activate
def test_live_call_limit_stops_before_extra_call(cache: JsonCache) -> None:
    responses.get(ENRICH_URL, json=hubspot())
    apollo = client(cache, max_live_calls=1)
    apollo.enrich("hubspot.com")
    with pytest.raises(LiveCallLimitReached):
        apollo.enrich("example.com")
    assert len(responses.calls) == 1


@responses.activate
def test_failed_call_still_counts_toward_limit(cache: JsonCache) -> None:
    responses.get(ENRICH_URL, status=500)
    apollo = client(cache, max_live_calls=1)
    with pytest.raises(SourceError):
        apollo.enrich("hubspot.com")
    with pytest.raises(LiveCallLimitReached):
        apollo.enrich("hubspot.com")
    assert len(responses.calls) == 1


@responses.activate
def test_cache_hits_do_not_count_toward_limit(cache: JsonCache) -> None:
    cache.put("apollo/hubspot.com.json", hubspot())
    apollo = client(cache, max_live_calls=0)
    for _ in range(3):
        apollo.enrich("hubspot.com")
    assert apollo.live_calls == 0


def test_negative_limit_rejected(cache: JsonCache) -> None:
    with pytest.raises(ValueError):
        client(cache, max_live_calls=-1)


def test_trim_keeps_kickoff_fields_with_types() -> None:
    org = trim(hubspot())
    assert org is not None
    assert org.annual_revenue == 2_600_000_000.0
    assert org.estimated_num_employees == 8500
    assert org.founded_year == 2005
    assert org.publicly_traded_symbol == "HUBS"
    assert org.state == "Massachusetts"
    assert org.sic_codes == ("7372",)
    assert org.naics_codes == ("513210",)
    assert org.total_funding is None
    assert org.latest_funding_stage is None


def test_trim_turns_wrong_types_into_none() -> None:
    raw = {
        "organization": {
            "name": 123,
            "annual_revenue": "2.6B",
            "estimated_num_employees": True,
            "founded_year": 2005.5,
            "sic_codes": "7372",
            "naics_codes": ["513210", 7, ""],
        }
    }
    org = trim(raw)
    assert org is not None
    assert org.name is None
    assert org.annual_revenue is None
    assert org.estimated_num_employees is None
    assert org.founded_year is None
    assert org.sic_codes == ()
    assert org.naics_codes == ("513210",)


@pytest.mark.parametrize(
    "raw", [{"organization": None}, {"organization": {}}, {"organization": "x"}]
)
def test_trim_returns_none_when_no_organization(raw: Any) -> None:
    assert trim(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("hubspot.com", "hubspot.com"),
        ("  HubSpot.COM ", "hubspot.com"),
        ("https://www.hubspot.com/about?x=1", "hubspot.com"),
        ("http://blog.hubspot.com", "blog.hubspot.com"),
    ],
)
def test_normalize_domain(raw: str, expected: str) -> None:
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "../etc/passwd", "hubspot", "hub spot.com", "-a.com", "a..com"]
)
def test_normalize_domain_rejects_non_domains(raw: str) -> None:
    with pytest.raises(ValueError, match="not a domain"):
        normalize_domain(raw)


@responses.activate
def test_object_without_organization_key_raises_and_writes_no_cache(cache: JsonCache) -> None:
    responses.get(ENRICH_URL, json={"error": "something went wrong"})
    with pytest.raises(SourceError, match="no 'organization' key"):
        client(cache).enrich("hubspot.com")
    assert cache.get("apollo/hubspot.com.json") is None


@responses.activate
def test_explicit_null_organization_is_cached_as_no_match(cache: JsonCache) -> None:
    responses.get(ENRICH_URL, json={"organization": None})
    assert client(cache).enrich("unknown.example") is None
    assert cache.get("apollo/unknown.example.json") == {"organization": None}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("https://hubspot.com:443/", "hubspot.com"), ("hubspot.com.", "hubspot.com")],
)
def test_normalize_domain_strips_port_and_trailing_dot(raw: str, expected: str) -> None:
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_trim_rejects_non_finite_numbers(value: float) -> None:
    org = trim({"organization": {"annual_revenue": value, "total_funding": value}})
    assert org is not None
    assert org.annual_revenue is None
    assert org.total_funding is None


@responses.activate
def test_windows_reserved_domain_gets_safe_cache_name(cache: JsonCache) -> None:
    responses.get(ENRICH_URL, json={"organization": None})
    assert client(cache).enrich("con.com") is None
    assert cache.get("apollo/con_.com.json") == {"organization": None}


def test_trim_handles_integers_too_big_for_float() -> None:
    org = trim({"organization": {"annual_revenue": 10**400, "total_funding": 5}})
    assert org is not None
    assert org.annual_revenue is None
    assert org.total_funding == 5.0
