# Probe notes (2026-11-20)

One live call to each source with `tools/probe.py --domain hubspot.com`. Raw responses stay in the gitignored `cache/`. Fixtures in `tests/fixtures/` are built from them by `tools/make_fixtures.py` (see [ADR 0001](adr/0001-fixtures-from-real-responses.md)).

## Apollo `GET /api/v1/organizations/enrich?domain=hubspot.com`

HTTP 200, 40 KB, one top-level key: `organization` (58 keys).

| KICKOFF field | Actual key | Type | Note |
|---|---|---|---|
| name | `name` | str | |
| domain | **`primary_domain`** | str | `domain` does not exist |
| annual_revenue | `annual_revenue` | float | |
| estimated_num_employees | `estimated_num_employees` | int | |
| founded_year | `founded_year` | int | |
| publicly_traded_symbol | `publicly_traded_symbol` | str | |
| publicly_traded_exchange | `publicly_traded_exchange` | str | lowercase, e.g. `nasdaq` |
| city | `city` | str | |
| state | `state` | str | **full name** (`Massachusetts`), SEC uses 2-letter codes |
| country | `country` | str | |
| industry | `industry` | str | lowercase label |
| sic_codes | `sic_codes` | list[str] | can hold several codes |
| naics_codes | `naics_codes` | list[str] | |
| total_funding | **absent** | | not returned for this public company; treat as optional |
| latest_funding_stage | **absent** | | same |

- Size: the bulk is `current_technologies` (28 KB), not subsidiaries (`suborganizations` is 3.7 KB).
- Response headers show request counters and limits, not credits: `x-24-hour-usage`, `x-hourly-usage`, `x-minute-usage`, `x-rate-limit-24-hour: 600`, `x-rate-limit-hourly: 200`, `x-rate-limit-minute: 50`.
- Credits: **one enrich call costs one credit.** The Apollo UI went from 1 to 2 of 85 used after this single call.

## SEC `company_tickers.json`

Object keyed by row number. Each row: `cik_str` (int), `ticker`, `title`. HUBS → CIK `0001404655`, `HUBSPOT INC`. Class shares use a dash (`BRK-B`).

## SEC `submissions/CIK0001404655.json`

| Need | Key | Example |
|---|---|---|
| Legal name | `name` | `HUBSPOT INC` |
| Former names | `formerNames` | `[]` (list) |
| SIC | `sic`, `sicDescription` | `"7372"` (string), `Services-Prepackaged Software` |
| Fiscal year end | `fiscalYearEnd` | `"1231"` (MMDD) |
| HQ state | `addresses.business.stateOrCountry` | `MA` |
| Exchange | `exchanges` | `["NYSE"]` |

- `filings.recent` is parallel arrays (1,003 rows here, back to 2018). Older pages are listed in `filings.files`; 12 months of 8-Ks fit in `recent`.
- **8-K items are one comma-separated string with no spaces**: `"5.02,7.01,9.01"`. Non-8-K rows have `""`.
- Filing link: `https://www.sec.gov/Archives/edgar/data/{cik}/{accession without dashes}/{primaryDocument}` → HTTP 200.
- Data conflict seen: Apollo says `nasdaq`, SEC says `NYSE`.

## SEC `companyfacts/CIK0001404655.json`

`facts.us-gaap.<Concept>.units.USD[]`, each row: `start`, `end`, `val`, `accn`, `fy`, `fp`, `form`, `filed`, `frame`.

- **Concept order is a trap.** `Revenues` exists but its latest annual value is FY2017 ($375.6M). Current revenue is in `RevenueFromContractWithCustomerExcludingAssessedTax` (FY2025: $3,131,266,000). See [ADR 0002](adr/0002-sec-annual-revenue-selection.md).
- **`fp == "FY"` on a 10-K does not mean a full year.** 10-Ks include quarterly rows (e.g. 2013-01-01 to 2013-03-31). Filter on duration.
- **`fy` is the filing's fiscal year, not the period's.** Label the period from `end`.
- Filing index link: `https://www.sec.gov/Archives/edgar/data/{cik}/{accession without dashes}/` → HTTP 200.
- Apollo's real `annual_revenue` matched SEC within 0.001%.
