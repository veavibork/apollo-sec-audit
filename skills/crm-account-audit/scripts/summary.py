"""Print a compact JSON summary of reports/audit.json: only what needs a person's attention."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from crm_audit.console import safe_output
from crm_audit.models import FieldResult
from crm_audit.reports import is_fix, needs_review

CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}
FACT_KINDS = ("legal_name", "fiscal_year_end", "founded_year")


def _item(account_id: str, name: str | None, field: FieldResult) -> dict[str, Any]:
    return {
        "account_id": account_id,
        "account": name,
        "field": field.field,
        "current": field.crm_value,
        "proposed": field.proposed_value,
        "source": field.winner,
        "confidence": field.confidence,
        "rationale": field.rationale,
        "evidence_url": field.evidence_url,
    }


def event_counts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filings per account and 8-K item, with the latest date."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for e in events:
        group = groups.setdefault(
            (e["account_id"], e["kind"]),
            {
                **{k: e[k] for k in ("account_id", "account", "kind", "label")},
                "count": 0,
                "latest": None,
            },
        )
        group["count"] += 1
        if e["date"] and (group["latest"] is None or e["date"] > group["latest"]):
            group["latest"] = e["date"]
    return [groups[key] for key in sorted(groups)]


def summarize(audit: Any) -> dict[str, Any]:
    if not isinstance(audit, dict) or not isinstance(audit.get("accounts"), list):
        raise ValueError("audit.json has no accounts list")
    fixes, review, events, facts, errors = [], [], [], [], []
    for entry in audit["accounts"]:
        try:
            account = entry["account"]
            account_id, name = str(account["account_id"]), account.get("name")
        except (KeyError, TypeError):
            raise ValueError("audit.json has an account without an account_id") from None
        if "error" in entry:
            errors.append({"account_id": account_id, "account": name, "error": entry["error"]})
            continue
        try:
            fields = [FieldResult(**f) for f in entry["fields"]]
            signals = [
                {k: s[k] for k in ("kind", "detail", "date", "url")} for s in entry["signals"]
            ]
            for s in signals:
                if not isinstance(s["kind"], str) or not isinstance(s["date"], str | None):
                    raise TypeError("signal kind must be text and date text or null")
            for f in fields:
                for value in (f.crm_value, f.apollo_value, f.sec_value, f.proposed_value):
                    if isinstance(value, bool) or not isinstance(value, str | int | float | None):
                        raise TypeError("field values must be text, numbers or null")
                for label in (f.field, f.status, f.rationale):
                    if not isinstance(label, str):
                        raise TypeError("field, status and rationale must be text")
                for optional in (f.winner, f.confidence, f.evidence_url):
                    if not isinstance(optional, str | None):
                        raise TypeError("winner, confidence and evidence_url must be text or null")
        except (KeyError, TypeError):
            raise ValueError(f"audit.json entry {account_id} is malformed") from None
        fixes += [_item(account_id, name, f) for f in fields if is_fix(f)]
        review += [_item(account_id, name, f) for f in fields if needs_review(f)]
        by_kind = {s["kind"]: s["detail"] for s in signals if s["kind"] in FACT_KINDS}
        facts.append(
            {
                "account_id": account_id,
                "account": name,
                "sec_status": entry.get("sec_status"),
                "ticker": entry.get("ticker"),
                **{kind: by_kind.get(kind) for kind in FACT_KINDS[:2]},
                "former_names": [s["detail"] for s in signals if s["kind"] == "former_name"],
                "founded_year": by_kind.get("founded_year"),
            }
        )
        events += [
            {
                "account_id": account_id,
                "account": name,
                "kind": s["kind"],
                "label": s["detail"],
                "date": s["date"],
                "url": s["url"],
            }
            for s in signals
            if s["kind"].startswith("8-K")
        ]
    fixes.sort(key=lambda f: (CONFIDENCE_ORDER.get(f["confidence"], 3), f["account_id"]))
    events.sort(key=lambda e: e["date"] or "", reverse=True)
    return {
        "event_counts": event_counts(events),
        "as_of": audit.get("as_of"),
        "apollo_live_calls": audit.get("apollo_live_calls"),
        "counts": {
            "accounts": len(audit["accounts"]),
            "fixes": len(fixes),
            "review": len(review),
            "events": len(events),
            "errors": len(errors),
        },
        "fixes": fixes,
        "review": review,
        "events": events,
        "facts": facts,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=Path("reports/audit.json"))
    args = parser.parse_args(argv)
    safe_output()
    if not args.audit.exists():
        print(f"error: {args.audit} not found; run audit.py first", file=sys.stderr)
        return 1
    try:
        result = summarize(json.loads(args.audit.read_text(encoding="utf-8")))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
