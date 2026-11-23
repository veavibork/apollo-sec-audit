# 0001. Test fixtures start from real responses, then Apollo values are replaced

## Context
Tests must run offline, so they need fixtures. Fixtures copied from live responses catch real field names and shapes; hand-written ones encode our assumptions. This repo is public. Apollo's response is Apollo's data, and committing it would redistribute it. SEC EDGAR data is public domain.

## Decision
- We made one real call to each source (`tools/probe.py`) and confirmed every field name against the live response ([probe notes](../probe-notes.md)).
- `tools/make_fixtures.py` builds the committed fixtures from those cached responses:
  - **Apollo:** keep the response shape and public identity facts (name, domain, ticker, exchange, city, state, country). **Replace Apollo's estimates and proprietary fields with fake values** (revenue, employees, founded year, industry, codes, technologies, keywords, subsidiaries). Then discard the raw response; it lives only in the gitignored `cache/`.
  - **SEC:** keep real values, trimmed to what tests need.
- We deliberately altered real data. In practice we would not: real fixtures would live in a private repo, so tests run against exactly what the vendor returns. We did it here only because the repo is public.

## Consequences
- Tests exercise the real Apollo shape without publishing Apollo's data.
- The fake Apollo revenue is about 17% below SEC's FY2025 figure, so the fixture exercises the conflict path. The real values agreed within 0.001%.
- If Apollo changes its schema, these fixtures won't show it. A scheduled live contract test would (see README, hardening).
- Re-running `tools/make_fixtures.py` needs the cached raw responses, so it costs one Apollo credit on a fresh machine.
- **Where the line is (decided 2026-11-23):** API responses, fixtures with real values, report files and any bulk Apollo data are never committed. The docs may quote a handful of individual Apollo values where one explains a finding: Google's founded year, Chick-fil-A's headcount, the company `deltafaucet.com` resolves to, a few SIC codes. That's commentary on specific findings, not redistribution of the dataset.
