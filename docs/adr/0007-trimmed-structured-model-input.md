# 0007. The model reads a trimmed, structured summary, not raw data

## Context
CLAUDE.md: "Structured data beats free text. Pass the model trimmed, typed fields, never raw API dumps." The Apollo response for one company is about 40 KB, mostly technology lists. The full `audit.json` for 12 accounts is about 40 KB, most of it fields that are `ok`. A model reading raw data spends context on noise, and it can be tempted to fill gaps or re-judge values the rules already settled.

## Decision
- Deterministic code does every judgment: matching, precedence, tolerances, confidence and status ([ADR 0004](0004-audit-rules.md)).
- `summary.py` reduces `audit.json` to what needs a person: proposed fixes, review items, 8-K events, key facts and errors. On the sample data that's 15 KB instead of 40 KB. It rebuilds each field as a typed `FieldResult` and reuses the reports' own fix and review rules, so the summary can't disagree with the CSVs.
- The summary also carries `event_counts`: filings per account and 8-K item, with the latest date. A cold test showed the model miscounting (8 NVIDIA executive changes instead of 7), so counting is done in code and the model quotes the numbers. The JSON is printed compact, without indentation.
- `SKILL.md` tells the model to read only that summary, to use only its values, and to keep confidence as reported.
- Approvals go through `apply_fixes.py --approve ACCOUNT:FIELD`, so the model runs one exact command instead of editing CSV cells.

## Consequences
- The model's job is narrow: run, explain, ask, apply. Its answer can be checked line by line against the summary.
- Anything the summary drops (for example `ok` fields) isn't visible to the model. A user who wants the full detail can open `reports/audit.json`.
- Changing what the model sees means changing `summary.py` and its tests, not the prompt.
