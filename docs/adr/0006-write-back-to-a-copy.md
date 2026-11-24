# 0006. Write approved fixes to a copy, never to the source

## Context
KICKOFF says a person approves every change. CLAUDE.md says: propose changes, never apply them without explicit approval, and never overwrite a value a person entered without flagging it. The audit writes proposals; something has to turn approvals into changes safely.

## Decision
- `audit.py` writes `reports/proposed_fixes.csv` with an empty `approved` column. Only high and medium items are listed; low items go to `needs_review.csv`. `apply_fixes.py` also refuses any row marked low, so a low item copied into the fixes file still can't be applied.
- A person marks rows `y` (or `yes`). `apply_fixes.py` applies only those rows to **`data/accounts.updated.csv`**. The input file is never written, and `--out` can't point at it.
- Each approved row is checked before it's applied:
  - the account exists and the field is editable;
  - the CRM value still equals the audit's `current_value`, so a value someone changed after the audit is skipped, not overwritten;
  - the proposed value parses for its field (number, two-letter US state, an industry label from `sic_industry.csv`);
  - only one approved row per account and field.
- Skipped rows are listed with a reason. The output is written to a temp file and renamed, so a failure never leaves a half-written file.
- An existing output file is never replaced without `--force`, because it may hold an earlier round. Without `--force`, the output is published with a create-if-absent step: a hard link, or an exclusive create where hard links aren't supported. A file that appears mid-run is never clobbered. A second round reads the previous output with `--accounts` and writes a new `--out`.
- `--approve ACCOUNT:FIELD` records approvals only after the output is written, so a failed write never leaves approvals that weren't applied. It refuses to turn a reviewer's `n` into `y`.
- Rerunning `audit.py` refuses to replace a `proposed_fixes.csv` that holds approvals, unless `--force` is passed. The check runs before any Apollo call.
- Every CSV cell that a spreadsheet would run as a formula (leading `=`, `+`, `-`, `@`, tab, CR, or `'`) gets a `'` prefix; `apply_fixes.py` removes it when reading.

## Consequences
- A diff of `accounts.csv` against `accounts.updated.csv` shows exactly what was approved.
- Writing to a live CRM is future work (README, "What I'd do next"); it would need the same guards plus the CRM's own audit trail.
- The fixes file is compared with what was read before each write, and the run stops if it changed. If recording approvals fails after the output was written, the output is removed. With `--force` it's kept, and the run reports that approvals weren't recorded, so check both files before retrying. This narrows the window for losing a concurrent edit but can't close it: an editor saving in the instant between check and write would still be overwritten. Likewise, two runs writing the same output at once (one with `--force`) could, if the other then fails, have its cleanup remove the forced run's file. Closing these gaps needs a lock every writer honors. For a single-user CLI that's out of proportion; a real CRM integration would use the CRM's own record locking.
- Approvals live in a CSV, so they're lost if someone deletes the file. That's acceptable for a file-based v1.
