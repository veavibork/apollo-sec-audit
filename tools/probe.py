"""One-off probe: fetch one Apollo org and its SEC records into cache/ to confirm field names."""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
APOLLO_URL = "https://api.apollo.io/api/v1/organizations/enrich"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
HEADER_HINTS = ("rate", "limit", "credit", "usage", "quota")


def save(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    print(f"  saved {path.relative_to(ROOT)} ({len(body):,} bytes)")


def fetch_apollo(domain: str) -> dict[str, Any]:
    path = CACHE / "apollo" / f"{domain}.json"
    if path.exists():
        print(f"Apollo: cache hit for {domain}, no credit spent")
        return dict(json.loads(path.read_bytes()))
    key = os.environ.get("APOLLO_API_KEY")
    if not key:
        sys.exit("APOLLO_API_KEY is not set")
    print(f"Apollo: live call for {domain} (spends a credit)")
    resp = requests.get(
        APOLLO_URL,
        params={"domain": domain},
        headers={"x-api-key": key, "Cache-Control": "no-cache", "accept": "application/json"},
        timeout=30,
    )
    print(f"  HTTP {resp.status_code}")
    usage = {k: v for k, v in resp.headers.items() if any(h in k.lower() for h in HEADER_HINTS)}
    save(CACHE / "apollo" / f"{domain}.headers.json", json.dumps(usage, indent=2).encode())
    resp.raise_for_status()
    save(path, resp.content)
    return dict(resp.json())


def fetch_sec(url: str, path: Path, user_agent: str) -> Any:
    if path.exists():
        print(f"SEC: cache hit {path.name}")
        return json.loads(path.read_bytes())
    time.sleep(0.2)
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=30)
    print(f"SEC: GET {url} -> HTTP {resp.status_code}")
    resp.raise_for_status()
    save(path, resp.content)
    return resp.json()


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    domain = parser.parse_args().domain

    org = fetch_apollo(domain).get("organization") or {}
    print(f"  organization keys: {len(org)}")
    ticker = org.get("publicly_traded_symbol")
    print(f"  publicly_traded_symbol: {ticker}")
    if not ticker:
        sys.exit("No ticker from Apollo; stopping before SEC")

    user_agent = os.environ.get("SEC_USER_AGENT")
    if not user_agent:
        sys.exit("SEC_USER_AGENT is not set")
    tickers = fetch_sec(SEC_TICKERS_URL, CACHE / "sec" / "company_tickers.json", user_agent)
    match = [row for row in tickers.values() if row["ticker"].upper() == ticker.upper()]
    if len(match) != 1:
        sys.exit(f"Expected one SEC row for {ticker}, found {len(match)}")
    cik = f"{int(match[0]['cik_str']):010d}"
    print(f"  {ticker} -> CIK {cik} ({match[0]['title']})")
    fetch_sec(
        SEC_SUBMISSIONS_URL.format(cik=cik), CACHE / "sec" / f"submissions_{cik}.json", user_agent
    )
    fetch_sec(SEC_FACTS_URL.format(cik=cik), CACHE / "sec" / f"companyfacts_{cik}.json", user_agent)


if __name__ == "__main__":
    main()
