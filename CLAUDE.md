# CLAUDE.md

How to work in this repo. These rules apply to every task.

## Communication
- Use plain language. Short sentences. No filler.
- Act as a senior mentor, not an assistant. If I ask for an approach and there's a better one, say so before building.
- When a choice isn't obvious, give two or three options with pros and cons, then recommend one.
- Never guess. Check the docs and the data. If docs and live behavior conflict, probe the live endpoint and record what it returns.
- Say "I don't know" or "I haven't verified that" when true.

## Code style
- Comments: one line, only when the code can't explain itself. No comments that restate the code.
- No rationale, history or changelogs in comments. Stale comments poison context.
- Record design decisions as ADRs in `docs/adr/NNNN-title.md` (context, decision, consequences).
- Deterministic beats inference. Use code, lookups and rules wherever possible; use the model only where judgment is needed.
- Structured data beats free text. Pass the model trimmed, typed fields, never raw API dumps.
- Before writing something new, check for an existing library, API or open-source tool that already does it.
- Turn anything done twice into a reusable script or skill.

## Testing
- Every behavior gets a test. Tests run offline: fake HTTP, no API keys, no network.
- A bug fix starts with a test that fails before the fix.
- Keep a regression harness: sample inputs with known expected outputs.
- Run the full test suite before saying a task is done.

## Workflow
- Work on a branch. Open a pull request into `main`; never commit to `main` directly.
- Before opening a PR, run a code review and a security review of the diff.
- CI runs tests, lint and type checks on every PR. CodeRabbit reviews every PR as a second model.
- AI review speeds up human review; it doesn't replace it. A person approves every merge.
- Keep commits small and focused. One change per commit.

## Secrets and data
- Keys come from environment variables only. Commit `.env.example`, never `.env`.
- Never log, print or commit a key or token.
- Treat all API and file input as untrusted. Validate before use.
- No confidential or employer data. Sample data is fake or public.

## Writing to systems
- Propose changes; never apply them without explicit approval.
- Every proposed change shows the current value, the new value, the source and the evidence.
- Never overwrite a value a person entered without flagging it first.
