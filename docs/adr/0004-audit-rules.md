# 0004. Audit rules as data, confidence by rule

## Context
KICKOFF asks for source precedence "as data, not prose" and for confidence set "by rules in code, never by the model." Several cases aren't covered by KICKOFF's tables: fields the CRM has no column for, industry labels from different vocabularies, and what a failed or borderline match does to confidence.

## Decision
- **Data** lives in `scripts/rules.toml`: field precedence, tolerances (revenue 15%, employees 15%), name-check thresholds (pass ≥ 90, borderline ≥ 70), revenue concepts, fields whose conflicts always go to review, and the 8-K items and window. `rules.py` validates the file and fails loudly on a bad value.
- **SIC → industry** lives in `scripts/sic_industry.csv` as code ranges. The narrowest matching range wins. A test checks that all 444 codes on SEC's SIC list map to a label.
- **Confidence** is code in `compare.py`:
  - SEC value → high. Apollo value → medium. These are the starting levels.
  - A source's trust caps it. A borderline SEC name check caps SEC at low. A failed SEC name check drops SEC data, as KICKOFF requires. A CRM name that doesn't match Apollo's, or a blank CRM or Apollo name, caps Apollo and SEC at low, because the SEC match came from Apollo's ticker.
  - A field in `review_on_conflict` (industry) drops to low on conflict. Low items go to the review list with the candidate value shown for a person to judge. They never go to the proposed fixes list.
- **Status:** `ok` (CRM agrees within tolerance), `missing` (CRM blank), `conflict` (CRM differs), `unverified` (no usable source).
- **Judgment calls:**
  1. Legal name, founded year, fiscal year end and former names are reported as additions, never as fixes. The CRM has no column for them, and a display name like "HubSpot" is not wrong because the legal name is "HUBSPOT INC".
  2. The CRM name is checked against Apollo's name, to catch a CRM domain that points to another company. A failed check produces a `domain` review item.
  3. Industry without SEC is `unverified`. Apollo's labels use another vocabulary ("information technology & services"), so comparing them to ours would be a guess. Apollo's label is still shown.
  4. A failed or borderline SEC match produces a `sec_match` review item, so it's visible even when every field agrees. A failed match reports `sec_status` as `name_check_failed`, not `matched`.

## Consequences
- Changing a threshold or precedence is a one-line edit with no code change. The golden cases in `tests/golden/cases.json` show what each change affects.
- Confidence is explainable: every rationale names the source, the rule and any cap.
- Additions never overwrite CRM data, at the cost of not filling columns a CRM admin might want to add.
