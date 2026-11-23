"""Build committed test fixtures from the probe's cached raw responses (see docs/adr/0001)."""

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
OUT = ROOT / "tests" / "fixtures"
CIK = "0001404655"

APOLLO_KEEP_REAL = {
    "name",
    "primary_domain",
    "website_url",
    "publicly_traded_symbol",
    "publicly_traded_exchange",
    "city",
    "state",
    "country",
}
APOLLO_FAKE = {
    "id": "000000000000000000000001",
    "annual_revenue": 2_600_000_000.0,
    "annual_revenue_printed": "2.6B",
    "estimated_num_employees": 8500,
    "founded_year": 2005,
    "industry": "computer software",
    "sic_codes": ["7372"],
    "naics_codes": ["513210"],
    "keywords": ["fake keyword"],
    "current_technologies": [{"uid": "fake_tech", "name": "Fake Tech", "category": "Other"}],
    "suborganizations": [{"id": "fake_sub", "name": "Fake Subsidiary", "website_url": None}],
    "short_description": "Fixture: Apollo estimates replaced with fake values.",
}
SEC_TICKERS_KEEP = {"HUBS", "BRK-B", "AAPL"}
REVENUE_CONCEPTS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
)
FILINGS_SINCE = "2025-06-01"


def dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size:,} bytes)")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def apollo() -> None:
    org = load(CACHE / "apollo" / "hubspot.com.json")["organization"]
    trimmed = {k: v for k, v in org.items() if k in APOLLO_KEEP_REAL}
    trimmed.update(APOLLO_FAKE)
    dump(OUT / "apollo" / "hubspot.com.json", {"organization": trimmed})


def sec_tickers() -> None:
    rows = load(CACHE / "sec" / "company_tickers.json")
    kept = {k: v for k, v in rows.items() if v["ticker"] in SEC_TICKERS_KEEP}
    dump(OUT / "sec" / "company_tickers.json", kept)


def sec_submissions() -> None:
    sub = load(CACHE / "sec" / f"submissions_{CIK}.json")
    recent = sub["filings"]["recent"]
    idx = [i for i, d in enumerate(recent["filingDate"]) if d >= FILINGS_SINCE]
    sub["filings"]["recent"] = {k: [v[i] for i in idx] for k, v in recent.items()}
    sub["filings"]["files"] = []
    dump(OUT / "sec" / f"submissions_{CIK}.json", sub)


def sec_companyfacts() -> None:
    facts = load(CACHE / "sec" / f"companyfacts_{CIK}.json")
    gaap = facts["facts"]["us-gaap"]
    facts["facts"] = {"us-gaap": {c: gaap[c] for c in REVENUE_CONCEPTS}}
    dump(OUT / "sec" / f"companyfacts_{CIK}.json", facts)


if __name__ == "__main__":
    apollo()
    sec_tickers()
    sec_submissions()
    sec_companyfacts()
