# 0005. Match SEC by ticker only; the name check is a sanity check

## Context
Linking an account to an SEC filer by name is error-prone. Names are reused, abbreviated and changed. KICKOFF says: match only by ticker via `company_tickers.json`, sanity-check that the SEC name resembles the Apollo name, and never guess a CIK from a name.

## Decision
- The ticker comes from Apollo's `publicly_traded_symbol`. The lookup tries the ticker as given and then SEC's dash form (`BRK.B` → `BRK-B`). A ticker that maps to two CIKs is treated as no match.
- The name check normalizes both names (case, punctuation, `&` → `and`, legal suffixes from `rules.toml`), then scores them with `rapidfuzz.token_set_ratio`.
- The Apollo name is compared to the SEC legal name and to every SEC former name, and the best score wins. "Google" matches Alphabet through its former name "Google Inc.".
- Pass, borderline and fail follow the thresholds in `rules.toml`; see ADR 0004 for what each does to confidence.

## Consequences
- No CIK is ever inferred from a name. Private companies get no SEC data (see KICKOFF on Form D).
- `token_set_ratio` scores a subset as 100: "Apple" vs "Apple Hospitality REIT" passes. That's acceptable only because the ticker, not the name, makes the match. The name check catches a wrong ticker, not a similar name. README lists a stronger check under hardening.
- The check is strict on partial overlaps. "Hubspot Software" vs "HUBSPOT SOLUTIONS INC" scores 66.7 and fails. A golden case pins this behavior.
