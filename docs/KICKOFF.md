# Kickoff: CRM Account Audit skill

Read CLAUDE.md first. Then read this whole file and propose a plan before writing code.

## Goal
Build an Agent Skill that audits CRM account records against Apollo and SEC EDGAR. It finds gaps, stale values and conflicts, proposes fixes with evidence, and adds well-supported facts the CRM doesn't have. A person approves every change.

This is a take-home for Apollo's Senior GTM Systems Engineer role. Timebox: about 3 hours including the write-up. Aim for a focused, working v1, not polish.

## Why it matters (for the README)
Reps and RevOps trust CRM firmographics that are often stale or estimated. Wrong revenue or industry data breaks territory assignment, scoring and routing. Public companies publish authoritative facts to the SEC for free; enrichment vendors estimate. Checking one against the other catches errors early and surfaces buying signals, like a new executive or an acquisition.

## Inputs
- `data/accounts.csv`: fake CRM accounts. Columns: `account_id, name, domain, annual_revenue, hq_state, industry, employees`.
- Seed about 10 to 15 real companies, mostly public, a few private. Put some deliberately stale or wrong values in, and leave some fields blank.

## Sources
1. **Apollo** organization enrichment: `GET https://api.apollo.io/api/v1/organizations/enrich?domain=...`, header `x-api-key`. Key from env `APOLLO_API_KEY`. One credit per call. Cache every raw response under `cache/apollo/` (gitignored) and reuse it; never spend credits in tests.
   - The raw response is about 180 KB, mostly subsidiaries. Trim it to the fields we use: name, domain, annual_revenue, estimated_num_employees, founded_year, publicly_traded_symbol, publicly_traded_exchange, city, state, country, industry, sic_codes, naics_codes, total_funding, latest_funding_stage.
2. **SEC EDGAR**, no key needed. Required header: `User-Agent: <name> <email>` from env `SEC_USER_AGENT`. Stay under 10 requests per second.
   - Ticker to CIK: `https://www.sec.gov/files/company_tickers.json`
   - Submissions: `https://data.sec.gov/submissions/CIK##########.json` (10-digit, zero-padded). Legal name, former names, SIC, fiscal year end, state of incorporation, business address, recent filings.
   - Company facts: `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`. Revenue from the latest full-year 10-K. Companies use different revenue concepts; check several (for example `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet`).
   - Verify every field name against a live response before relying on it. In particular, confirm how 8-K event item codes appear in the submissions file.

## Matching
- Match Apollo to SEC only through the ticker, via `company_tickers.json`. That's an exact lookup, not name matching.
- Sanity-check the match: SEC legal name should resemble the Apollo name. If not, flag it; don't use it.
- No ticker means no SEC match. Never guess a CIK from a name in v1.

## Comparison rules (source precedence)
Encode these as data, not prose, so they're easy to change:

| Field | Winner | Notes |
|---|---|---|
| Annual revenue | SEC (latest 10-K) | Flag if Apollo or CRM differs by more than 15% |
| Legal name | SEC | |
| HQ state | SEC business address | Not state of incorporation |
| Industry | SEC SIC code | Keep Apollo's label for display |
| Employees | Apollo | SEC doesn't report it reliably |
| Founded year | Apollo | |

## Confidence and rationale
Every value the audit proposes carries a confidence level and a one-line rationale. Confidence is set by rules in code, never by the model.

| Confidence | When |
|---|---|
| High | SEC value, matched by exact ticker, name sanity check passed |
| Medium | Apollo value with no SEC value to check against, or SEC and Apollo agree within tolerance |
| Low | Sources conflict with no authoritative winner, or the name sanity check is borderline |

- Low-confidence items go to a "needs review" list. They are never proposed as fixes.
- The rationale names the source and the rule, for example: "SEC 10-K FY2025 revenue; Apollo estimate differs by 22%."

## Additions (facts the CRM doesn't hold)
- Fiscal year end (budget timing)
- Former names (catches renames and duplicates)
- Recent 8-K events, last 12 months, by item code:
  - 5.02 executive change
  - 2.01 completed acquisition
  - 2.05 restructuring or layoffs
  - 1.01 material agreement
- Each with filing date and a link to the filing.

## Outputs
- `reports/audit.json`: per account, each field with CRM / Apollo / SEC values, the winner, a status (`ok`, `missing`, `conflict`, `unverified`), confidence and rationale.
- `reports/proposed_fixes.csv`: `account_id, field, current_value, proposed_value, source, evidence_url, confidence, rationale`. High and medium only.
- `reports/needs_review.csv`: low-confidence items, same columns.
- `reports/signals.csv`: the additions above.

## The skill
`skills/crm-account-audit/SKILL.md` with YAML frontmatter (`name`, `description`) plus a `scripts/` folder.
- The description says when to use it: auditing account records, checking firmographics, or finding buying signals.
- Instructions: run the audit script, read `audit.json`, summarize the biggest problems first, explain each proposed fix in plain language with its evidence, and never apply a change without approval.
- The model reasons over the trimmed, structured output only. It never fetches or invents data itself.

## Deliberately out of scope for v1
Private-company SEC lookups (Form D), writing to a live CRM, people and contact data, scraping filing text. List these in the README under "What I'd do next," each with its reason. For Form D, the reason is: private companies have no ticker, so linking them to an SEC filer means name matching, and a wrong match is worse than no match. Doing it safely needs a name-plus-state-plus-funding-date check, with weak matches sent to review. That didn't fit the timebox.

## Repo basics
- Python 3.12, pytest, the `responses` library for fake HTTP.
- `.env.example`, `.gitignore` (cache, reports, .env), GitHub Actions CI running tests and lint.
- README: problem, setup, how to run, sample output, assumptions, design decisions, what was pre-existing vs. new, where AI helped and where I overrode it, what I'd harden for production.

## Order of work
Stop after each step and show me the result.
1. Probe Apollo once (one domain) and SEC once (one CIK). Save the raw responses as test fixtures. Confirm field names.
2. Build the trimmed source clients, with tests against the fixtures.
3. Build matching and comparison, with tests.
4. Generate the reports from sample data.
5. Write the SKILL.md and run the skill end to end.
6. README, ADRs for the key decisions, CI.
