# 0003. Apollo credit guardrails

## Context
Each Apollo enrich call costs one credit ([probe notes](../probe-notes.md)), and the plan has 85 per cycle. A rerun, a bug in a loop or a bad cache entry could spend them without anyone noticing. SEC is free but asks for fewer than 10 requests per second.

## Decision
- **Cache first.** `ApolloClient.enrich` reads `cache/apollo/{domain}.json` before calling. A cached domain never costs a credit and doesn't need `APOLLO_API_KEY`.
- **Cache the whole parsed response, never raw bytes.** A body is saved only after it parses and has the expected shape, so a bad response can't stick in the cache. Writes are atomic. Trimming happens on read, so changing the trimmed fields costs no credits.
- **Corrupt cache files raise.** They are not treated as a miss, because a silent refetch spends a credit.
- **Hard cap per run.** `ApolloClient` takes `max_live_calls`; the audit CLI sets it from `APOLLO_MAX_LIVE_CALLS` (default 15). A call is counted before it is sent, since a failed call may still cost a credit. Hitting the cap raises `LiveCallLimitReached`; the run stops instead of skipping accounts.
- **Domains are validated** before they become cache file names, so CRM input can't write outside `cache/`.
- **SEC throttle** at 8 requests per second, live calls only.
- **Tests never call either API.** `pytest-socket` blocks the network and `responses` fakes HTTP.

## Consequences
- Reruns are free once a domain is cached.
- Cached data never expires. A stale cache means stale values; delete the file to refetch. See README, "What I'd harden for production".
- Counting attempts can stop a run one call early if the failed call was in fact free. That's the safe side to err on.
