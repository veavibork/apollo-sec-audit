"""Audit CRM accounts against Apollo and SEC EDGAR, then write reports."""

import argparse
import csv
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from crm_audit.accounts import load_accounts
from crm_audit.apollo import ApolloClient, cache_key, normalize_domain
from crm_audit.cache import JsonCache
from crm_audit.compare import compare_account
from crm_audit.errors import LiveCallLimitReached, SourceError
from crm_audit.matching import find_sec
from crm_audit.models import Account, AccountAudit
from crm_audit.reports import AccountError, write_reports
from crm_audit.rules import IndustryMap, Rules, load_industries, load_rules
from crm_audit.sec import SecClient

DEFAULT_MAX_LIVE_CALLS = 15


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=Path, default=Path("data/accounts.csv"))
    parser.add_argument("--out", type=Path, default=Path("reports"))
    parser.add_argument("--cache", type=Path, default=Path("cache"))
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--live", action="store_true", help="allow live Apollo calls (one credit each)"
    )
    parser.add_argument("--max-live-calls", type=int, default=None)
    parser.add_argument(
        "--force", action="store_true", help="overwrite a proposed_fixes.csv that has approvals"
    )
    return parser.parse_args(argv)


def max_live_calls(flag: int | None) -> int:
    if flag is not None:
        if flag < 0:
            raise ValueError("--max-live-calls must be 0 or more")
        return flag
    raw = os.environ.get("APOLLO_MAX_LIVE_CALLS", "").strip()
    if not raw:
        return DEFAULT_MAX_LIVE_CALLS
    if not raw.isdigit():
        raise ValueError("APOLLO_MAX_LIVE_CALLS must be a whole number")
    return int(raw)


def uncached_domains(accounts: list[Account], cache: JsonCache) -> list[str]:
    domains = []
    for account in accounts:
        try:
            domain = normalize_domain(account.domain or "")
        except ValueError:
            continue
        try:
            cached = cache.get(cache_key(domain))
        except SourceError:
            continue
        if cached is None and domain not in domains:
            domains.append(domain)
    return domains


def has_approvals(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open(encoding="utf-8-sig", newline="") as f:
        return any((row.get("approved") or "").strip() for row in csv.DictReader(f))


def audit_one(
    account: Account,
    apollo: ApolloClient,
    sec: SecClient,
    cache: JsonCache,
    live: bool,
    rules: Rules,
    industries: IndustryMap,
    as_of: date,
) -> AccountAudit | AccountError:
    try:
        org = None
        if account.domain is not None:
            domain = normalize_domain(account.domain)
            if not live and cache.get(cache_key(domain)) is None:
                return AccountError(account, f"{domain} is not cached; rerun with --live")
            org = apollo.enrich(domain)
        lookup = find_sec(org, account.name, sec, rules)
        return compare_account(account, org, lookup, rules, industries, as_of)
    except LiveCallLimitReached:
        raise
    except (SourceError, ValueError) as exc:
        return AccountError(account, str(exc))


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv)
    try:
        rules, industries = load_rules(), load_industries()
        accounts = load_accounts(args.accounts)
        cap = max_live_calls(args.max_live_calls)
        cache = JsonCache(args.cache)
        sec = SecClient(cache, os.environ.get("SEC_USER_AGENT", ""))
        key = os.environ.get("APOLLO_API_KEY", "").strip() or None
        if args.live and key is None:
            raise ValueError("--live needs APOLLO_API_KEY in the environment or .env")
        fixes_path = args.out / "proposed_fixes.csv"
        if not args.force and has_approvals(fixes_path):
            raise ValueError(
                f"{fixes_path} has approvals that a rerun would erase. "
                "Apply them with apply_fixes.py, then rerun with --force "
                "(add --accounts data/accounts.updated.csv to audit the applied values)"
            )
        apollo = ApolloClient(cache, key if args.live else None, max_live_calls=cap)
    except (OSError, ValueError, SourceError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    pending = uncached_domains(accounts, cache)
    print(f"{len(accounts)} accounts; {len(pending)} domains not in the Apollo cache.")
    if pending and args.live:
        print(f"Live run: up to {min(len(pending), cap)} Apollo credits (cap {cap}).")
    elif pending:
        print("Dry run: those accounts are skipped. Rerun with --live to fetch them.")

    results: list[AccountAudit | AccountError] = []
    try:
        for account in accounts:
            results.append(
                audit_one(account, apollo, sec, cache, args.live, rules, industries, args.as_of)
            )
    except LiveCallLimitReached as exc:
        print(f"error: {exc}. No reports written; cached calls are kept.", file=sys.stderr)
        return 2
    finally:
        print(f"Apollo live calls this run: {apollo.live_calls}")

    meta = {"as_of": args.as_of.isoformat(), "apollo_live_calls": apollo.live_calls}
    counts = write_reports(results, args.out, meta)
    print(
        f"Wrote {args.out}: {counts['fixes']} proposed fixes, {counts['review']} for review, "
        f"{counts['signals']} signals, {counts['errors']} account errors."
    )
    for result in results:
        if isinstance(result, AccountError):
            print(f"  {result.account.account_id}: {result.error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
