from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ApolloOrg:
    name: str | None
    domain: str | None
    annual_revenue: float | None
    estimated_num_employees: int | None
    founded_year: int | None
    publicly_traded_symbol: str | None
    publicly_traded_exchange: str | None
    city: str | None
    state: str | None
    country: str | None
    industry: str | None
    sic_codes: tuple[str, ...]
    naics_codes: tuple[str, ...]
    total_funding: float | None
    latest_funding_stage: str | None


@dataclass(frozen=True)
class TickerMatch:
    cik: str
    ticker: str
    title: str


@dataclass(frozen=True)
class FormerName:
    name: str
    from_date: date | None
    to_date: date | None


@dataclass(frozen=True)
class Filing:
    form: str
    filing_date: date
    accession: str
    items: tuple[str, ...]
    url: str
    index_url: str


@dataclass(frozen=True)
class SecCompany:
    cik: str
    name: str
    former_names: tuple[FormerName, ...]
    sic: str | None
    sic_description: str | None
    fiscal_year_end: str | None
    business_state: str | None
    exchanges: tuple[str, ...]
    filings: tuple[Filing, ...]


@dataclass(frozen=True)
class SecRevenue:
    value: float
    concept: str
    period_start: date
    period_end: date
    filed: date
    accession: str
    index_url: str


@dataclass(frozen=True)
class Account:
    account_id: str
    name: str | None
    domain: str | None
    annual_revenue: float | None
    hq_state: str | None
    industry: str | None
    employees: int | None


@dataclass(frozen=True)
class NameCheck:
    score: float
    verdict: str
    compared_to: str


@dataclass(frozen=True)
class SecLookup:
    status: str
    ticker: str | None = None
    match: TickerMatch | None = None
    company: SecCompany | None = None
    revenue: SecRevenue | None = None
    name_check: NameCheck | None = None


@dataclass(frozen=True)
class FieldResult:
    field: str
    crm_value: str | float | int | None
    apollo_value: str | float | int | None
    sec_value: str | float | int | None
    winner: str | None
    proposed_value: str | float | int | None
    status: str
    confidence: str | None
    rationale: str
    evidence_url: str | None


@dataclass(frozen=True)
class Signal:
    kind: str
    detail: str
    source: str
    date: date | None
    url: str | None


@dataclass(frozen=True)
class AccountAudit:
    account: Account
    sec_status: str
    ticker: str | None
    cik: str | None
    fields: tuple[FieldResult, ...]
    signals: tuple[Signal, ...]
