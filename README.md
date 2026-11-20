# apollo-sec-audit

An Agent Skill that audits CRM account records against Apollo and SEC EDGAR, proposes evidence-backed fixes, and surfaces buying signals. A person approves every change.

Work in progress. Full write-up lands in Step 6 of [docs/KICKOFF.md](docs/KICKOFF.md).

## What I'd harden for production

- **Pin GitHub Actions to commit SHAs.** CI uses tags (`actions/checkout@v4`). A moved or compromised tag would run new code in CI.
- **Lock dependency versions.** `pyproject.toml` uses `>=` ranges with no lock file, so two installs can differ. Use a lock file (e.g. `uv lock` or `pip-tools`) and update it on purpose.
