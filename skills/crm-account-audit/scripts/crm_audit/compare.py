"""Field-by-field comparison of a CRM account against Apollo and SEC. Pure: no I/O."""

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date

from crm_audit.matching import FAIL, PASS, check_name
from crm_audit.models import (
    Account,
    AccountAudit,
    ApolloOrg,
    FieldResult,
    SecLookup,
    Signal,
)
from crm_audit.rules import IndustryMap, Rules
from crm_audit.signals import sec_signals
from crm_audit.states import state_code

HIGH, MEDIUM, LOW = "high", "medium", "low"
_RANK = {LOW: 0, MEDIUM: 1, HIGH: 2}
BASE_CONFIDENCE = {"sec": HIGH, "apollo": MEDIUM}
SOURCE_NAME = {"sec": "SEC", "apollo": "Apollo"}
Value = str | float | int


@dataclass(frozen=True)
class Evidence:
    value: Value
    label: str
    url: str | None


@dataclass(frozen=True)
class Trust:
    usable: bool
    cap: str
    note: str


UNUSABLE = Trust(False, LOW, "")


def _min_confidence(a: str, b: str) -> str:
    return a if _RANK[a] <= _RANK[b] else b


def money(value: float) -> str:
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= size:
            return f"${value / size:.2f}{suffix}"
    return f"${value:,.0f}"


def _relative_diff(crm: float, winner: float) -> float:
    if winner == 0:
        return 0.0 if crm == 0 else math.inf
    return abs(crm - winner) / abs(winner)


def _percent(diff: float) -> str:
    return "an undefined amount" if math.isinf(diff) else f"{diff:.0%}"


def _normalize_label(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold().replace("&", "and")).strip()


Agree = Callable[[Value, Value], tuple[bool, str]]


def numeric_agree(tolerance: float) -> Agree:
    def agree(crm: Value, winner: Value) -> tuple[bool, str]:
        diff = _relative_diff(float(crm), float(winner))
        if diff <= tolerance:
            return True, f"CRM within {tolerance:.0%}"
        return False, f"CRM differs by {_percent(diff)}"

    return agree


def state_agree(crm: Value, winner: Value) -> tuple[bool, str]:
    code = state_code(str(crm))
    if code is None:
        return False, f"CRM value '{crm}' is not a US state"
    return (True, "CRM matches") if code == winner else (False, f"CRM says {code}")


def label_agree(crm: Value, winner: Value) -> tuple[bool, str]:
    if _normalize_label(str(crm)) == _normalize_label(str(winner)):
        return True, "CRM matches"
    return False, f"CRM says '{crm}'"


def apollo_trust(
    account: Account, org: ApolloOrg | None, rules: Rules
) -> tuple[Trust, list[FieldResult]]:
    if org is None:
        return UNUSABLE, []
    if not account.name or not org.name:
        return Trust(True, HIGH, ""), []
    check = check_name(account.name, [org.name], rules.name_match)
    if check.verdict == PASS:
        return Trust(True, HIGH, ""), []
    note = (
        f"CRM name '{account.name}' vs Apollo '{org.name}' "
        f"name check {check.verdict} ({check.score})"
    )
    review = FieldResult(
        field="domain",
        crm_value=account.domain,
        apollo_value=org.name,
        sec_value=None,
        winner=None,
        proposed_value=None,
        status="conflict",
        confidence=LOW,
        rationale=f"{note}; the CRM domain may belong to a different company.",
        evidence_url=None,
    )
    return Trust(True, LOW, note), [review]


def sec_trust(lookup: SecLookup, apollo: Trust) -> tuple[Trust, list[FieldResult]]:
    company, check = lookup.company, lookup.name_check
    if lookup.status != "matched" or company is None or check is None or lookup.match is None:
        return UNUSABLE, []
    if check.verdict == PASS:
        trust = Trust(True, HIGH, "")
        reviews: list[FieldResult] = []
    else:
        note = (
            f"ticker {lookup.ticker} maps to SEC '{company.name}' (CIK {lookup.match.cik}); "
            f"name check {check.verdict} ({check.score})"
        )
        used = "SEC data not used" if check.verdict == FAIL else "SEC data used at low confidence"
        reviews = [
            FieldResult(
                field="sec_match",
                crm_value=None,
                apollo_value=lookup.ticker,
                sec_value=company.name,
                winner=None,
                proposed_value=None,
                status="conflict",
                confidence=LOW,
                rationale=f"{note[0].upper()}{note[1:]}; {used}.",
                evidence_url=None,
            )
        ]
        trust = UNUSABLE if check.verdict == FAIL else Trust(True, LOW, note)
    if trust.usable and apollo.cap != HIGH:
        notes = "; ".join(n for n in (trust.note, apollo.note) if n)
        trust = Trust(True, _min_confidence(trust.cap, apollo.cap), notes)
    return trust, reviews


def resolve(
    field: str,
    crm: Value | None,
    evidence: dict[str, Evidence | None],
    trust: dict[str, Trust],
    rules: Rules,
    agree: Agree,
    display: dict[str, Value | None] | None = None,
) -> FieldResult:
    shown = {s: (e.value if e else None) for s, e in evidence.items()} | (display or {})
    usable = {s: e for s, e in evidence.items() if e is not None and trust[s].usable}
    winner = next((s for s in rules.precedence[field] if s in usable), None)

    unverified = FieldResult(
        field=field,
        crm_value=crm,
        apollo_value=shown.get("apollo"),
        sec_value=shown.get("sec"),
        winner=winner,
        proposed_value=None,
        status="unverified",
        confidence=None,
        rationale="No usable SEC or Apollo value.",
        evidence_url=None,
    )
    if winner is None:
        return unverified

    chosen = usable[winner]
    confidence = _min_confidence(BASE_CONFIDENCE[winner], trust[winner].cap)
    parts = [chosen.label]
    proposed: Value | None
    if crm is None:
        status, proposed = "missing", chosen.value
        parts.append("CRM is blank")
    else:
        ok, detail = agree(crm, chosen.value)
        status, proposed = ("ok", None) if ok else ("conflict", chosen.value)
        parts.append(detail)
        if not ok and field in rules.review_on_conflict:
            confidence = LOW
            parts.append(f"{field} conflicts always go to review")
    for source, other in usable.items():
        if source != winner and isinstance(other.value, int | float):
            diff = _relative_diff(float(other.value), float(chosen.value))
            parts.append(f"{SOURCE_NAME[source]} differs by {_percent(diff)}")
    if trust[winner].note:
        parts.append(trust[winner].note)
    return replace(
        unverified,
        proposed_value=proposed,
        status=status,
        confidence=confidence,
        rationale="; ".join(parts) + ".",
        evidence_url=chosen.url,
    )


def compare_account(
    account: Account,
    org: ApolloOrg | None,
    lookup: SecLookup,
    rules: Rules,
    industries: IndustryMap,
    as_of: date,
) -> AccountAudit:
    a_trust, reviews = apollo_trust(account, org, rules)
    s_trust, sec_reviews = sec_trust(lookup, a_trust)
    trust = {"apollo": a_trust, "sec": s_trust}
    company = lookup.company if s_trust.usable else None
    revenue = lookup.revenue if s_trust.usable else None

    sec_revenue = (
        Evidence(
            revenue.value,
            f"SEC 10-K FY{revenue.period_end.year} revenue {money(revenue.value)} "
            f"(period ending {revenue.period_end.isoformat()})",
            revenue.index_url,
        )
        if revenue
        else None
    )
    apollo_revenue = (
        Evidence(org.annual_revenue, f"Apollo revenue estimate {money(org.annual_revenue)}", None)
        if org and org.annual_revenue is not None
        else None
    )
    sec_state_code = state_code(company.business_state) if company else None
    apollo_state_code = state_code(org.state) if org else None
    industry = industries.label(company.sic) if company else None
    employees = org.estimated_num_employees if org else None

    fields = [
        resolve(
            "annual_revenue",
            account.annual_revenue,
            {"sec": sec_revenue, "apollo": apollo_revenue},
            trust,
            rules,
            numeric_agree(rules.tolerance["annual_revenue"]),
        ),
        resolve(
            "hq_state",
            account.hq_state,
            {
                "sec": Evidence(
                    sec_state_code, f"SEC business address state {sec_state_code}", None
                )
                if sec_state_code
                else None,
                "apollo": Evidence(apollo_state_code, f"Apollo HQ state {apollo_state_code}", None)
                if apollo_state_code
                else None,
            },
            trust,
            rules,
            state_agree,
        ),
        resolve(
            "industry",
            account.industry,
            {
                "sec": Evidence(
                    industry,
                    f"SEC SIC {company.sic} ({company.sic_description}) maps to {industry}",
                    None,
                )
                if company and industry
                else None,
                "apollo": None,
            },
            trust,
            rules,
            label_agree,
            display={"apollo": org.industry if org else None},
        ),
        resolve(
            "employees",
            account.employees,
            {
                "sec": None,
                "apollo": Evidence(employees, f"Apollo employee estimate {employees:,}", None)
                if employees is not None
                else None,
            },
            trust,
            rules,
            numeric_agree(rules.tolerance["employees"]),
        ),
    ]

    signals: list[Signal] = []
    if company is not None and s_trust.cap == HIGH:
        signals.extend(sec_signals(company, rules, as_of))
    if org is not None and a_trust.cap == HIGH and org.founded_year is not None:
        signals.append(Signal("founded_year", str(org.founded_year), "apollo", None, None))

    return AccountAudit(
        account=account,
        sec_status=lookup.status,
        ticker=lookup.ticker,
        cik=lookup.match.cik if lookup.match else None,
        fields=(*fields, *reviews, *sec_reviews),
        signals=tuple(signals),
    )
