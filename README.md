# apollo-sec-audit

An Agent Skill that audits CRM account records against Apollo and SEC EDGAR, proposes evidence-backed fixes, and surfaces buying signals. A person approves every change.

Work in progress. Full write-up lands in Step 6 of [docs/KICKOFF.md](docs/KICKOFF.md).

## What I'd harden for production

- **Pin GitHub Actions to commit SHAs.** CI uses tags (`actions/checkout@v4`). A moved or compromised tag would run new code in CI.
- **Lock dependency versions.** `pyproject.toml` uses `>=` ranges with no lock file, so two installs can differ. Use a lock file (e.g. `uv lock` or `pip-tools`) and update it on purpose.
- **Live contract tests.** Fixtures are snapshots ([ADR 0001](docs/adr/0001-fixtures-from-real-responses.md)). If Apollo or SEC change a field, offline tests still pass. Run a scheduled job that calls each API once and checks the fields we read still exist.
- **GitHub Code Quality.** Not enabled: its billing for public repos was unclear, and ruff, mypy, CodeQL and CodeRabbit already cover most of it. Revisit with a paid plan.
