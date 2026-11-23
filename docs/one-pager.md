# CRM Account Audit: one-pager

## What I built

An Agent Skill for Claude Code that audits CRM account records against **SEC EDGAR** and **Apollo**. It:
- proposes fixes, each with a source, a rule-based confidence level and a link to the evidence
- surfaces buying signals from SEC filings
- changes nothing until a person approves specific rows

## Why it matters to a GTM team

- **Routing, territories and scoring run on firmographics.** A stale revenue figure or the wrong HQ state sends an account to the wrong rep or tier. For public companies, the audit replaces estimates with what the company filed, and links the filing so approval takes seconds.
- **The filings themselves are signals.** SEC: companies must file most 8-Ks "within four business days of the triggering event" ([SEC Investor Bulletin](https://www.sec.gov/files/readan8k.pdf)). The skill flags executive changes (5.02), acquisitions (2.01), restructurings (2.05) and material agreements (1.01) from the last 12 months, plus fiscal year ends for budget timing.
- **Honest about evidence.** Every claim in the [value case](value-case.md) is labeled as sourced, research or hypothesis. Revenue impact isn't asserted; it's framed as something Apollo can measure with its own data, for example meeting and win rates after a 5.02 filing against a control group.

## Results on sample data

| | |
|---|---|
| Accounts | 12 real companies (9 public, 3 private), fake CRM values |
| Planted errors caught | **10 of 10**, each at the expected confidence |
| Real findings, not planted | google.com has no ticker in Apollo (the parent is Alphabet); an Apollo headcount that appears to count corporate staff only; a wrong founded year in Apollo |
| Output | 12 proposed fixes, 6 for review, 32 8-K events |
| Apollo credits | 11 for the live run; reruns are free from the cache |

## How it works

```text
CRM CSV ──domain──► Apollo enrich ──ticker──► SEC: tickers → submissions + companyfacts
                                    │
             rules.toml: precedence, tolerances, confidence (code, not the model)
                                    │
     reports/ ──► summary.py (15 KB of typed JSON) ──► Claude explains, asks, applies
                                    │
               apply_fixes.py --approve ──► accounts.updated.csv (input never edited)
```

**Systems touched:**
- a CRM export (CSV, read and written)
- the Apollo Organization Enrichment API
- the SEC EDGAR APIs (tickers, submissions, XBRL company facts)
- Claude Code

## Key design choices

- **Deterministic code judges; the model explains.** Matching, precedence, tolerances and confidence all live in code and `rules.toml`. Even filing counts are pre-computed after a test caught the model miscounting.
- **SEC is matched only by ticker,** never by guessing from a name. Name checks guard both hops, and they caught a CRM domain that pointed to Delta Faucet instead of Delta Air Lines.
- **Approval is built in.**
  - Low-confidence items can't be applied: `apply_fixes.py` refuses them.
  - Each approved row must still match the value the audit saw.
  - Writes go to a copy.
- **Credits are guarded.** Dry run by default, cache first, and a hard cap on live calls.

## How it was built and checked

- Built with Claude Code.
- **341 offline tests**, including a hand-written golden harness and mutation checks.
- Two AI reviews before every PR and a third (CodeRabbit) after. A person approved each merge.
- A cold test in a fresh session that saw only `SKILL.md`.

## Next

- private companies through SEC Form D
- parent and subsidiary linking
- an optional CRM ticker column
- a live CRM write with the same guards
- reading filing text, linked to contacts

Details are in the [README](../README.md).
