# apollo-sec-audit

An Agent Skill that audits CRM account records against Apollo and SEC EDGAR, proposes evidence-backed fixes, and surfaces buying signals. A person approves every change.

Work in progress. Full write-up lands in Step 6 of [docs/KICKOFF.md](docs/KICKOFF.md).

## What I'd harden for production

- **Pin GitHub Actions to commit SHAs.** CI uses tags (`actions/checkout@v4`). A moved or compromised tag would run new code in CI.
- **Lock dependency versions.** `pyproject.toml` uses `>=` ranges with no lock file, so two installs can differ. Use a lock file (e.g. `uv lock` or `pip-tools`) and update it on purpose.
- **Live contract tests.** Fixtures are snapshots ([ADR 0001](docs/adr/0001-fixtures-from-real-responses.md)). If Apollo or SEC change a field, offline tests still pass. Run a scheduled job that calls each API once and checks the fields we read still exist.
- **GitHub Code Quality.** Not enabled: its billing for public repos was unclear, and ruff, mypy, CodeQL and CodeRabbit already cover most of it. Revisit with a paid plan.
- **Cache expiry.** Cached responses never expire ([ADR 0003](docs/adr/0003-apollo-credit-guardrails.md)). SEC's ticker list and filings change daily, so a long-lived cache misses new 8-Ks. Give SEC entries a TTL (e.g. one day) and Apollo entries a longer one tied to the credit budget.
- **Retries with backoff.** A 429 or 5xx fails the account at once. Retry SEC calls with backoff; retry Apollo only within the credit cap.
- **Shared rate limit.** The SEC throttle is per process. Two runs at once could exceed 10 requests per second. Use a shared limiter if runs go parallel.
- **Stronger name check.** `token_set_ratio` passes subsets ("Apple" vs "Apple Hospitality REIT"; [ADR 0005](docs/adr/0005-ticker-matching-and-name-check.md)). Add a second signal, such as `token_sort_ratio` or the HQ state, before trusting the match.
- **Paid CodeRabbit tier.** The free tier allows about one review per hour. So minor findings that don't change a PR's behavior are deferred to the next step's PR, where they're fixed test-first, instead of waiting an hour for a re-review. The PR thread names the PR that fixes each one. With a paid tier, fix and re-review in the same PR.
