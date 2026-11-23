# 0006. Write approved fixes to a copy, never to the source

## Context
KICKOFF says a person approves every change. CLAUDE.md says: propose changes, never apply them without explicit approval, and never overwrite a value a person entered without flagging it. The audit writes proposals; something has to turn approvals into changes safely.

## Decision
- `audit.py` writes `reports/proposed_fixes.csv` with an empty `approved` column. Only high and medium items are listed; low items go to `needs_review.csv` and can't be applied.
- A person marks rows `y` (or `yes`). `apply_fixes.py` applies only those rows to **`data/accounts.updated.csv`**. The input file is never written, and `--out` can't point at it.
- Each approved row is checked before it's applied:
  - the account exists and the field is editable;
  - the CRM value still equals the audit's `current_value`, so a value someone changed after the audit is skipped, not overwritten;
  - the proposed value parses for its field (number, two-letter US state, an industry label from `sic_industry.csv`);
  - only one approved row per account and field.
- Skipped rows are listed with a reason. The output is written to a temp file and renamed, so a failure never leaves a half-written file.
- Rerunning `audit.py` refuses to replace a `proposed_fixes.csv` that holds approvals, unless `--force` is passed. The check runs before any Apollo call.
- Every CSV cell that a spreadsheet would run as a formula (leading `=`, `+`, `-`, `@`, tab, CR, or `'`) gets a `'` prefix; `apply_fixes.py` removes it when reading.

## Consequences
- A diff of `accounts.csv` against `accounts.updated.csv` shows exactly what was approved.
- Writing to a live CRM is future work (README, "What I'd do next"); it would need the same guards plus the CRM's own audit trail.
- Approvals live in a CSV, so they're lost if someone deletes the file. That's acceptable for a file-based v1.
