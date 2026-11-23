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
