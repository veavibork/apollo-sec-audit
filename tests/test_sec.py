from datetime import date
from typing import Any

import pytest
import responses
from responses import matchers

from crm_audit.cache import JsonCache
from crm_audit.errors import SourceError
from crm_audit.sec import (
    FACTS_URL,
    SUBMISSIONS_URL,
    TICKERS_URL,
    SecClient,
    Throttle,
    archive_url,
    normalize_cik,
    parse_company,
    parse_filings,
    select_annual_revenue,
    ticker_candidates,
)
from support import HUBS_CIK, USER_AGENT, load_fixture


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def client(cache: JsonCache) -> SecClient:
    fake = FakeClock()
    return SecClient(cache, USER_AGENT, throttle=Throttle(0.125, fake.clock, fake.sleep))


def submissions() -> Any:
    return load_fixture(f"sec/submissions_{HUBS_CIK}.json")


def facts() -> Any:
    return load_fixture(f"sec/companyfacts_{HUBS_CIK}.json")


def revenue_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "start": "2025-01-01",
        "end": "2025-12-31",
        "val": 100,
        "accn": "0000000000-26-000001",
        "form": "10-K",
        "filed": "2026-02-01",
    }
    return row | overrides


def facts_with(rows_by_concept: dict[str, list[Any]]) -> dict[str, Any]:
    gaap = {c: {"units": {"USD": rows}} for c, rows in rows_by_concept.items()}
    return {"facts": {"us-gaap": gaap}}


@responses.activate
def test_ticker_lookup_sends_user_agent_and_caches(cache: JsonCache) -> None:
    responses.get(
        TICKERS_URL,
        json=load_fixture("sec/company_tickers.json"),
        match=[matchers.header_matcher({"User-Agent": USER_AGENT})],
    )
    sec = client(cache)
    match = sec.cik_for_ticker("HUBS")
    assert match is not None
    assert (match.cik, match.ticker, match.title) == (HUBS_CIK, "HUBS", "HUBSPOT INC")
    assert sec.cik_for_ticker("aapl") is not None
    assert len(responses.calls) == 1
    assert cache.get("sec/company_tickers.json") is not None


@pytest.mark.parametrize("ticker", ["BRK.B", "brk-b", "BRK/B"])
def test_class_share_ticker_formats_match(cache: JsonCache, ticker: str) -> None:
    cache.put("sec/company_tickers.json", load_fixture("sec/company_tickers.json"))
    match = client(cache).cik_for_ticker(ticker)
    assert match is not None and match.cik == "0001067983"


def test_dotted_sec_ticker_matches_as_given(cache: JsonCache) -> None:
    cache.put("sec/company_tickers.json", {"0": {"cik_str": 7, "ticker": "SHO.PRI", "title": "X"}})
    match = client(cache).cik_for_ticker("sho.pri")
    assert match is not None and match.cik == "0000000007"


@pytest.mark.parametrize("ticker", ["ZZZZ", "", "NOT A TICKER", "../x"])
def test_unknown_or_malformed_ticker_returns_none(cache: JsonCache, ticker: str) -> None:
    cache.put("sec/company_tickers.json", load_fixture("sec/company_tickers.json"))
    assert client(cache).cik_for_ticker(ticker) is None


def test_ticker_with_two_ciks_returns_none(cache: JsonCache) -> None:
    rows = {
        "0": {"cik_str": 1, "ticker": "DUP", "title": "A"},
        "1": {"cik_str": 2, "ticker": "DUP", "title": "B"},
    }
    cache.put("sec/company_tickers.json", rows)
    assert client(cache).cik_for_ticker("DUP") is None


def test_ticker_candidates() -> None:
    assert ticker_candidates(" brk.b ") == ("BRK.B", "BRK-B")
    assert ticker_candidates("HUBS") == ("HUBS",)
    assert ticker_candidates("TOOLONGTICKER") == ()


@responses.activate
def test_company_from_submissions(cache: JsonCache) -> None:
    responses.get(SUBMISSIONS_URL.format(cik=HUBS_CIK), json=submissions())
    company = client(cache).company(1404655)
    assert company.name == "HUBSPOT INC"
    assert company.sic == "7372"
    assert company.sic_description == "Services-Prepackaged Software"
    assert company.fiscal_year_end == "1231"
    assert company.business_state == "MA"
    assert company.exchanges == ("NYSE",)
    assert company.former_names == ()
    assert len(company.filings) == len(submissions()["filings"]["recent"]["form"])


def test_filing_items_split_and_urls_built() -> None:
    company = parse_company(HUBS_CIK, submissions())
    eight_k = next(f for f in company.filings if f.form == "8-K" and f.items)
    assert all("," not in i and i == i.strip() for i in eight_k.items)
    assert eight_k.index_url == archive_url(HUBS_CIK, eight_k.accession)
    assert eight_k.index_url.startswith("https://www.sec.gov/Archives/edgar/data/1404655/")
    assert eight_k.url.startswith(eight_k.index_url) and eight_k.url != eight_k.index_url


def test_filing_items_parse_known_values() -> None:
    recent = {
        "form": ["8-K", "10-Q"],
        "filingDate": ["2026-01-05", "2026-02-01"],
        "accessionNumber": ["0001193125-26-000001", "0001193125-26-000002"],
        "items": ["5.02,7.01,9.01", ""],
        "primaryDocument": ["d1 8k.htm", "q.htm"],
    }
    eight_k, ten_q = parse_filings(HUBS_CIK, recent)
    assert eight_k.items == ("5.02", "7.01", "9.01")
    assert eight_k.filing_date == date(2026, 1, 5)
    assert eight_k.url.endswith("/000119312526000001/d1%208k.htm")
    assert ten_q.items == ()


def test_filings_with_mismatched_columns_raise() -> None:
    recent = {
        "form": ["8-K"],
        "filingDate": [],
        "accessionNumber": [],
        "items": [],
        "primaryDocument": [],
    }
    with pytest.raises(SourceError, match="differ in length"):
        parse_filings(HUBS_CIK, recent)


def test_filings_with_bad_accession_are_skipped() -> None:
    recent = {
        "form": ["8-K"],
        "filingDate": ["2026-01-05"],
        "accessionNumber": ["../../evil"],
        "items": ["5.02"],
        "primaryDocument": ["x.htm"],
    }
    assert parse_filings(HUBS_CIK, recent) == ()


def test_former_names_parse_live_shape() -> None:
    raw = submissions() | {
        "formerNames": [
            {
                "name": "Facebook Inc",
                "from": "2005-05-06T04:00:00.000Z",
                "to": "2021-10-27T04:00:00.000Z",
            },
            {"name": None},
        ]
    }
    (former,) = parse_company(HUBS_CIK, raw).former_names
    assert former.name == "Facebook Inc"
    assert former.from_date == date(2005, 5, 6)
    assert former.to_date == date(2021, 10, 27)


def test_company_without_name_raises() -> None:
    with pytest.raises(SourceError, match="no name"):
        parse_company(HUBS_CIK, {"filings": {}})


@responses.activate
def test_annual_revenue_from_fixture_uses_latest_concept(cache: JsonCache) -> None:
    responses.get(FACTS_URL.format(cik=HUBS_CIK), json=facts())
    revenue = client(cache).annual_revenue(HUBS_CIK)
    assert revenue is not None
    assert revenue.value == 3_131_266_000
    assert revenue.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert revenue.period_end == date(2025, 12, 31)
    assert revenue.accession == "0001193125-26-046646"
    assert (
        revenue.index_url == "https://www.sec.gov/Archives/edgar/data/1404655/000119312526046646/"
    )


def test_revenue_skips_quarterly_rows_in_10k() -> None:
    raw = facts_with(
        {
            "Revenues": [
                revenue_row(start="2025-10-01", end="2025-12-31", val=30),
                revenue_row(start="2024-01-01", end="2024-12-31", val=90),
            ]
        }
    )
    revenue = select_annual_revenue(HUBS_CIK, raw)
    assert revenue is not None and revenue.value == 90


def test_revenue_skips_non_10k_and_non_usd() -> None:
    raw = facts_with({"Revenues": [revenue_row(form="10-Q"), revenue_row(form="8-K")]})
    raw["facts"]["us-gaap"]["SalesRevenueNet"] = {"units": {"EUR": [revenue_row()]}}
    assert select_annual_revenue(HUBS_CIK, raw) is None


def test_revenue_accepts_53_week_year() -> None:
    raw = facts_with({"Revenues": [revenue_row(start="2025-01-01", end="2026-01-04")]})
    assert select_annual_revenue(HUBS_CIK, raw) is not None


def test_revenue_tie_breaks_by_latest_filed() -> None:
    raw = facts_with(
        {
            "Revenues": [
                revenue_row(val=100, filed="2026-02-01"),
                revenue_row(val=105, filed="2026-06-01", accn="0000000000-26-000002"),
            ]
        }
    )
    revenue = select_annual_revenue(HUBS_CIK, raw)
    assert revenue is not None and revenue.value == 105


def test_revenue_same_period_and_filing_prefers_earlier_concept() -> None:
    raw = facts_with(
        {
            "Revenues": [revenue_row(val=100)],
            "RevenueFromContractWithCustomerExcludingAssessedTax": [revenue_row(val=99)],
        }
    )
    revenue = select_annual_revenue(HUBS_CIK, raw)
    assert revenue is not None and revenue.concept == "Revenues"


def test_revenue_skips_malformed_rows() -> None:
    raw = facts_with(
        {
            "Revenues": [
                revenue_row(val="lots"),
                revenue_row(start=None),
                "junk",
                revenue_row(accn="x"),
            ]
        }
    )
    assert select_annual_revenue(HUBS_CIK, raw) is None


@pytest.mark.parametrize("raw", [{}, {"facts": "x"}, None])
def test_revenue_missing_facts_returns_none(raw: Any) -> None:
    assert select_annual_revenue(HUBS_CIK, raw) is None


@responses.activate
def test_sec_http_error_writes_no_cache(cache: JsonCache) -> None:
    responses.get(SUBMISSIONS_URL.format(cik=HUBS_CIK), status=503)
    with pytest.raises(SourceError, match="HTTP 503"):
        client(cache).company(HUBS_CIK)
    assert cache.get(f"sec/submissions_{HUBS_CIK}.json") is None


@responses.activate
def test_sec_invalid_json_writes_no_cache(cache: JsonCache) -> None:
    responses.get(FACTS_URL.format(cik=HUBS_CIK), body="<html>", status=200)
    with pytest.raises(SourceError, match="not valid JSON"):
        client(cache).annual_revenue(HUBS_CIK)
    assert cache.get(f"sec/companyfacts_{HUBS_CIK}.json") is None


@responses.activate
def test_sec_non_object_json_writes_no_cache(cache: JsonCache) -> None:
    responses.get(TICKERS_URL, json=[1, 2])
    with pytest.raises(SourceError, match="not return a JSON object"):
        client(cache).cik_for_ticker("HUBS")
    assert cache.get("sec/company_tickers.json") is None


@responses.activate
def test_sec_cache_hit_makes_no_call(cache: JsonCache) -> None:
    cache.put(f"sec/submissions_{HUBS_CIK}.json", submissions())
    assert client(cache).company(HUBS_CIK).name == "HUBSPOT INC"
    assert len(responses.calls) == 0


@pytest.mark.parametrize("agent", ["", "no-email", "a@b.com"])
def test_user_agent_needs_name_and_email(cache: JsonCache, agent: str) -> None:
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        SecClient(cache, agent)


@pytest.mark.parametrize("raw", ["abc", "12345678901", -1, "../1"])
def test_normalize_cik_rejects_bad_input(raw: str | int) -> None:
    with pytest.raises(ValueError, match="not a CIK"):
        normalize_cik(raw)


def test_normalize_cik_pads() -> None:
    assert normalize_cik(1404655) == HUBS_CIK
    assert normalize_cik("1404655") == HUBS_CIK


def test_throttle_sleeps_only_for_remaining_interval() -> None:
    fake = FakeClock()
    throttle = Throttle(0.125, fake.clock, fake.sleep)
    throttle.wait()
    fake.now += 0.05
    throttle.wait()
    fake.now += 1.0
    throttle.wait()
    assert fake.slept == [pytest.approx(0.075)]


def test_document_with_slashes_cannot_leave_filing_folder() -> None:
    recent = {
        "form": ["8-K"],
        "filingDate": ["2026-01-05"],
        "accessionNumber": ["0001193125-26-000001"],
        "items": ["5.02"],
        "primaryDocument": ["../../../../x.htm"],
    }
    (filing,) = parse_filings(HUBS_CIK, recent)
    assert filing.url.startswith(filing.index_url)
    assert "/" not in filing.url.removeprefix(filing.index_url)


def test_normalize_cik_rejects_non_ascii_digits() -> None:
    with pytest.raises(ValueError, match="not a CIK"):
        normalize_cik("１４０４６５５")


@pytest.mark.parametrize(
    ("url", "bad", "call"),
    [
        (TICKERS_URL, {}, lambda sec: sec.cik_for_ticker("HUBS")),
        (TICKERS_URL, {"0": "x"}, lambda sec: sec.cik_for_ticker("HUBS")),
        (SUBMISSIONS_URL.format(cik=HUBS_CIK), {}, lambda sec: sec.company(HUBS_CIK)),
        (
            SUBMISSIONS_URL.format(cik=HUBS_CIK),
            {"name": "X", "filings": {}},
            lambda sec: sec.company(HUBS_CIK),
        ),
        (FACTS_URL.format(cik=HUBS_CIK), {"cik": 1}, lambda sec: sec.annual_revenue(HUBS_CIK)),
    ],
)
@responses.activate
def test_invalid_body_is_not_cached_and_valid_retry_is_used(
    cache: JsonCache, url: str, bad: Any, call: Any
) -> None:
    good = {
        TICKERS_URL: load_fixture("sec/company_tickers.json"),
        SUBMISSIONS_URL.format(cik=HUBS_CIK): submissions(),
        FACTS_URL.format(cik=HUBS_CIK): facts(),
    }[url]
    responses.get(url, json=bad)
    responses.get(url, json=good)
    sec = client(cache)
    with pytest.raises(SourceError, match="missing required fields"):
        call(sec)
    assert call(sec) is not None
    assert len(responses.calls) == 2


def test_company_with_empty_recent_filings_is_valid(cache: JsonCache) -> None:
    empty: dict[str, list[str]] = {
        k: [] for k in ("form", "filingDate", "accessionNumber", "items", "primaryDocument")
    }
    raw = submissions() | {"filings": {"recent": empty, "files": []}}
    cache.put(f"sec/submissions_{HUBS_CIK}.json", raw)
    assert client(cache).company(HUBS_CIK).filings == ()


@pytest.mark.parametrize(
    ("url", "bad", "call"),
    [
        (TICKERS_URL, {"0": {}}, lambda sec: sec.cik_for_ticker("HUBS")),
        (
            SUBMISSIONS_URL.format(cik=HUBS_CIK),
            {"name": "X", "filings": {"recent": {}}},
            lambda sec: sec.company(HUBS_CIK),
        ),
    ],
)
@responses.activate
def test_bodies_that_fail_parsing_are_not_cached(
    cache: JsonCache, url: str, bad: Any, call: Any
) -> None:
    responses.get(url, json=bad)
    with pytest.raises(SourceError, match="missing required fields"):
        call(client(cache))
    assert list(cache.root.rglob("*.json")) == []


@responses.activate
def test_missing_companyfacts_means_no_revenue(cache: JsonCache) -> None:
    responses.get(FACTS_URL.format(cik=HUBS_CIK), status=404, body="<Error/>")
    assert client(cache).annual_revenue(HUBS_CIK) is None
    assert cache.get(f"sec/companyfacts_{HUBS_CIK}.json") is None


@responses.activate
def test_companyfacts_server_error_still_raises(cache: JsonCache) -> None:
    responses.get(FACTS_URL.format(cik=HUBS_CIK), status=503)
    with pytest.raises(SourceError, match="HTTP 503"):
        client(cache).annual_revenue(HUBS_CIK)
