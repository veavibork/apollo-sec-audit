"""Fetch one Apollo org and its SEC records through the clients and print the trimmed results."""

import argparse
import os
import sys
from dataclasses import asdict, replace
from pathlib import Path
from pprint import pprint

from dotenv import load_dotenv

from crm_audit.apollo import ApolloClient
from crm_audit.cache import JsonCache
from crm_audit.errors import SourceError
from crm_audit.sec import SecClient

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None, root: Path = ROOT) -> None:
    load_dotenv(root / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True)
    domain = parser.parse_args(argv).domain
    cache = JsonCache(root / "cache")
    try:
        sec = SecClient(cache, os.environ.get("SEC_USER_AGENT", ""))
        apollo = ApolloClient(cache, os.environ.get("APOLLO_API_KEY"), max_live_calls=1)
        try:
            org = apollo.enrich(domain)
        finally:
            print(f"Apollo live calls: {apollo.live_calls}")
        if org is None:
            sys.exit(f"Apollo has no organization for {domain}")
        print("Apollo:")
        pprint(asdict(org))
        if org.publicly_traded_symbol is None:
            sys.exit("No ticker from Apollo; stopping before SEC")
        match = sec.cik_for_ticker(org.publicly_traded_symbol)
        if match is None:
            sys.exit(f"No single SEC match for ticker {org.publicly_traded_symbol}")
        company = sec.company(match.cik)
        print(f"SEC: {match.ticker} -> CIK {match.cik}, {len(company.filings)} recent filings")
        pprint(asdict(replace(company, filings=())))
        print("SEC annual revenue:")
        revenue = sec.annual_revenue(match.cik)
        pprint(asdict(revenue) if revenue else None)
    except (SourceError, ValueError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
