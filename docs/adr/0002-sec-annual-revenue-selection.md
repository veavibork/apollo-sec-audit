# 0002. SEC annual revenue: latest full-year fact across all revenue concepts

## Context
Companies tag revenue under different XBRL concepts, and switch concepts over time. KICKOFF suggested checking concepts in priority order. The probe showed that this gives the wrong answer: HubSpot's `Revenues` concept stops at FY2017 ($375.6M), while current revenue is in `RevenueFromContractWithCustomerExcludingAssessedTax` (FY2025: $3.13B). Taking the first concept found would report revenue eight years stale and about 8× too low.

The probe also showed that 10-K rows marked `fp: "FY"` include quarterly figures, and that `fy` labels the filing year, not the period.

## Decision
Collect rows from every candidate concept, then keep a row only if:
- `form` is `10-K`, and
- the unit is `USD`, and
- the period (`end - start`) is 350 to 380 days.

From those, pick the row with the latest `end`; break ties by the latest `filed`, which picks up restatements. Label the period by the year of `end`. Link to the filing index built from `accn`.

## Consequences
- Concept switches can't produce stale revenue.
- 52/53-week fiscal years fit inside the 350–380 day window.
- If a company stops filing (delisted or acquired), the latest value can still be old. Show the period end date in the rationale so a reviewer can see how old it is.
