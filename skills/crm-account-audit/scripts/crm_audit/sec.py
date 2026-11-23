import re
import time
from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import quote

import requests

from crm_audit.cache import JsonCache
from crm_audit.coerce import as_date, as_dict, as_float, as_str, as_str_tuple
from crm_audit.errors import SourceError
from crm_audit.fetch import get_json
from crm_audit.models import Filing, FormerName, SecCompany, SecRevenue, TickerMatch

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
REVENUE_CONCEPTS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
)
ANNUAL_DAYS = range(350, 381)
MIN_INTERVAL_SECONDS = 0.125
CIK_PATTERN = re.compile(r"^[0-9]{10}$")
TICKER_PATTERN = re.compile(r"^[A-Z0-9]{1,6}(?:-[A-Z0-9]{1,3})?$")
ACCESSION_PATTERN = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")


def ticker_candidates(raw: str) -> tuple[str, ...]:
    """'brk.b' -> ('BRK.B', 'BRK-B'): the given form first, then SEC's dash form."""
    upper = raw.strip().upper()
    dashed = upper.replace(".", "-").replace("/", "-")
    if not TICKER_PATTERN.fullmatch(dashed):
        return ()
    return tuple(dict.fromkeys((upper, dashed)))


def normalize_cik(raw: str | int) -> str:
    text = f"{raw:010d}" if isinstance(raw, int) else raw.strip().zfill(10)
    if not CIK_PATTERN.fullmatch(text):
        raise ValueError(f"not a CIK: {raw!r}")
    return text


def archive_url(cik: str, accession: str) -> str:
    return ARCHIVE_URL.format(cik=int(cik), accession=accession.replace("-", ""))


class Throttle:
    def __init__(
        self,
        min_interval: float = MIN_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        if self._last is not None:
            remaining = self._min_interval - (self._clock() - self._last)
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._clock()


def parse_filings(cik: str, recent: Any) -> tuple[Filing, ...]:
    recent = as_dict(recent)
    columns = ("form", "filingDate", "accessionNumber", "items", "primaryDocument")
    arrays = [recent.get(c) for c in columns]
    if not all(isinstance(a, list) for a in arrays):
        raise SourceError(f"sec: submissions {cik} is missing filing columns")
    if len({len(a) for a in arrays if isinstance(a, list)}) != 1:
        raise SourceError(f"sec: submissions {cik} filing columns differ in length")
    filings = []
    for form, filed, accession, items, document in zip(*arrays, strict=True):
        form_s, filed_d, acc_s, doc_s = (
            as_str(form),
            as_date(filed),
            as_str(accession),
            as_str(document),
        )
        if (
            form_s is None
            or filed_d is None
            or acc_s is None
            or not ACCESSION_PATTERN.fullmatch(acc_s)
        ):
            continue
        index = archive_url(cik, acc_s)
        item_codes = tuple(i.strip() for i in (as_str(items) or "").split(",") if i.strip())
        filings.append(
            Filing(
                form=form_s,
                filing_date=filed_d,
                accession=acc_s,
                items=item_codes,
                url=index + quote(doc_s, safe="") if doc_s else index,
                index_url=index,
            )
        )
    return tuple(filings)


def parse_former_names(raw: Any) -> tuple[FormerName, ...]:
    if not isinstance(raw, list):
        return ()
    names = []
    for entry in raw:
        entry = as_dict(entry)
        name = as_str(entry.get("name"))
        if name is not None:
            names.append(FormerName(name, as_date(entry.get("from")), as_date(entry.get("to"))))
    return tuple(names)


def parse_company(cik: str, raw: Any) -> SecCompany:
    raw = as_dict(raw)
    name = as_str(raw.get("name"))
    if name is None:
        raise SourceError(f"sec: submissions {cik} has no name")
    business = as_dict(as_dict(raw.get("addresses")).get("business"))
    return SecCompany(
        cik=cik,
        name=name,
        former_names=parse_former_names(raw.get("formerNames")),
        sic=as_str(raw.get("sic")),
        sic_description=as_str(raw.get("sicDescription")),
        fiscal_year_end=as_str(raw.get("fiscalYearEnd")),
        business_state=as_str(business.get("stateOrCountry")),
        exchanges=as_str_tuple(raw.get("exchanges")),
        filings=parse_filings(cik, as_dict(raw.get("filings")).get("recent")),
    )


def select_annual_revenue(
    cik: str, raw: Any, concepts: Iterable[str] = REVENUE_CONCEPTS
) -> SecRevenue | None:
    """Latest full-year 10-K revenue across all concepts. See docs/adr/0002."""
    gaap = as_dict(as_dict(as_dict(raw).get("facts")).get("us-gaap"))
    candidates = []
    for priority, concept in enumerate(concepts):
        rows = as_dict(as_dict(gaap.get(concept)).get("units")).get("USD")
        for row in rows if isinstance(rows, list) else []:
            revenue = _annual_10k_row(cik, concept, row)
            if revenue is not None:
                candidates.append(((revenue.period_end, revenue.filed, -priority), revenue))
    if not candidates:
        return None
    return max(candidates, key=lambda c: c[0])[1]


def _annual_10k_row(cik: str, concept: str, raw: Any) -> SecRevenue | None:
    row = as_dict(raw)
    if row.get("form") != "10-K":
        return None
    start, end, filed = (
        as_date(row.get("start")),
        as_date(row.get("end")),
        as_date(row.get("filed")),
    )
    value, accession = as_float(row.get("val")), as_str(row.get("accn"))
    if start is None or end is None or filed is None or value is None or accession is None:
        return None
    if (end - start).days not in ANNUAL_DAYS or not ACCESSION_PATTERN.fullmatch(accession):
        return None
    return SecRevenue(value, concept, start, end, filed, accession, archive_url(cik, accession))


def valid_tickers(raw: dict[str, Any]) -> bool:
    return bool(raw) and all(isinstance(row, dict) for row in raw.values())


def valid_submissions(raw: dict[str, Any]) -> bool:
    recent = as_dict(raw.get("filings")).get("recent")
    return as_str(raw.get("name")) is not None and isinstance(recent, dict)


def valid_facts(raw: dict[str, Any]) -> bool:
    return isinstance(raw.get("facts"), dict)


class SecClient:
    def __init__(
        self,
        cache: JsonCache,
        user_agent: str,
        session: requests.Session | None = None,
        throttle: Throttle | None = None,
    ) -> None:
        if "@" not in user_agent or " " not in user_agent.strip():
            raise ValueError('SEC_USER_AGENT must be "Name email@example.com"')
        self._cache = cache
        self._headers = {"User-Agent": user_agent.strip()}
        self._session = session or requests.Session()
        self._throttle = throttle or Throttle()
        self._tickers: dict[str, list[TickerMatch]] | None = None

    def _get(self, key: str, url: str, valid: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        data = self._cache.get(key)
        if data is None:
            self._throttle.wait()
            data = get_json(self._session, "sec", url, headers=self._headers)
            if not isinstance(data, dict):
                raise SourceError(f"sec: {url} did not return a JSON object")
            if not valid(data):
                raise SourceError(f"sec: {url} is missing required fields")
            self._cache.put(key, data)
        return as_dict(data)

    def _ticker_index(self) -> dict[str, list[TickerMatch]]:
        if self._tickers is None:
            index: dict[str, list[TickerMatch]] = {}
            for row in as_dict(
                self._get("sec/company_tickers.json", TICKERS_URL, valid_tickers)
            ).values():
                row = as_dict(row)
                ticker, title, cik = (
                    as_str(row.get("ticker")),
                    as_str(row.get("title")),
                    row.get("cik_str"),
                )
                if (
                    ticker is None
                    or title is None
                    or not isinstance(cik, int)
                    or isinstance(cik, bool)
                ):
                    continue
                index.setdefault(ticker.upper(), []).append(
                    TickerMatch(normalize_cik(cik), ticker, title)
                )
            self._tickers = index
        return self._tickers

    def cik_for_ticker(self, ticker: str) -> TickerMatch | None:
        """Exact ticker lookup. None if unknown or if the ticker maps to more than one CIK."""
        index = self._ticker_index()
        for candidate in ticker_candidates(ticker):
            matches = index.get(candidate)
            if matches:
                return matches[0] if len({m.cik for m in matches}) == 1 else None
        return None

    def company(self, cik: str | int) -> SecCompany:
        cik = normalize_cik(cik)
        return parse_company(
            cik,
            self._get(
                f"sec/submissions_{cik}.json", SUBMISSIONS_URL.format(cik=cik), valid_submissions
            ),
        )

    def annual_revenue(self, cik: str | int) -> SecRevenue | None:
        cik = normalize_cik(cik)
        return select_annual_revenue(
            cik, self._get(f"sec/companyfacts_{cik}.json", FACTS_URL.format(cik=cik), valid_facts)
        )
