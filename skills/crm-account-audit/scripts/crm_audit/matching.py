import re
from collections.abc import Iterable, Sequence
from typing import Protocol

from rapidfuzz import fuzz

from crm_audit.models import (
    ApolloOrg,
    NameCheck,
    SecCompany,
    SecLookup,
    SecRevenue,
    TickerMatch,
)
from crm_audit.rules import NameMatchRules, Rules

PASS, BORDERLINE, FAIL = "pass", "borderline", "fail"


class SecSource(Protocol):
    def cik_for_ticker(self, ticker: str) -> TickerMatch | None: ...

    def company(self, cik: str | int) -> SecCompany: ...

    def annual_revenue(
        self, cik: str | int, concepts: Iterable[str] = ...
    ) -> SecRevenue | None: ...


def normalize_name(name: str, strip_words: frozenset[str]) -> str:
    words = re.findall(r"[^\W_]+", name.casefold().replace("&", " and "))
    kept = [w for w in words if w not in strip_words]
    return " ".join(kept or words)


def check_name(name: str, candidates: Sequence[str], rules: NameMatchRules) -> NameCheck:
    """Best token-set score of `name` against any candidate, with a pass/borderline/fail verdict."""
    target = normalize_name(name, rules.strip_words)
    best_score, best_name = 0.0, candidates[0] if candidates else ""
    for candidate in candidates:
        other = normalize_name(candidate, rules.strip_words)
        score = fuzz.token_set_ratio(target, other) if target and other else 0.0
        if score > best_score:
            best_score, best_name = score, candidate
    if best_score >= rules.pass_score:
        verdict = PASS
    elif best_score >= rules.borderline_score:
        verdict = BORDERLINE
    else:
        verdict = FAIL
    return NameCheck(round(best_score, 1), verdict, best_name)


def find_sec(
    org: ApolloOrg | None, crm_name: str | None, sec: SecSource, rules: Rules
) -> SecLookup:
    """Ticker-only SEC lookup. The name check runs against the legal name and former names."""
    if org is None:
        return SecLookup("no_apollo_org")
    ticker = org.publicly_traded_symbol
    if ticker is None:
        return SecLookup("no_ticker")
    match = sec.cik_for_ticker(ticker)
    if match is None:
        return SecLookup("ticker_not_in_sec", ticker=ticker)
    company = sec.company(match.cik)
    revenue = sec.annual_revenue(match.cik, rules.revenue_concepts)
    name = org.name or crm_name or ""
    candidates = [company.name, *(f.name for f in company.former_names)]
    return SecLookup(
        "matched",
        ticker=ticker,
        match=match,
        company=company,
        revenue=revenue,
        name_check=check_name(name, candidates, rules.name_match),
    )
