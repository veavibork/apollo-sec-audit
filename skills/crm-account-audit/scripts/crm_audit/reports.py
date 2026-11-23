import csv
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from crm_audit.accounts import EDITABLE
from crm_audit.models import Account, AccountAudit, FieldResult

FIX_COLUMNS = (
    "account_id",
    "field",
    "current_value",
    "proposed_value",
    "source",
    "evidence_url",
    "confidence",
    "rationale",
)
SIGNAL_COLUMNS = ("account_id", "account_name", "kind", "detail", "date", "source", "url")
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class AccountError:
    account: Account
    error: str


def is_fix(result: FieldResult) -> bool:
    return (
        result.field in EDITABLE
        and result.status in ("missing", "conflict")
        and result.confidence in ("high", "medium")
        and result.proposed_value is not None
    )


def needs_review(result: FieldResult) -> bool:
    return result.confidence == "low" and result.status in ("missing", "conflict")


def cell(value: object) -> str:
    """Spreadsheet-safe text. Strings that a spreadsheet would run as a formula get a ' prefix."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    if isinstance(value, str) and text.startswith((*FORMULA_PREFIXES, "'")):
        return "'" + text
    return text


def uncell(text: str) -> str:
    if text.startswith("'") and text[1:].startswith((*FORMULA_PREFIXES, "'")):
        return text[1:]
    return text


def _fix_row(account_id: str, result: FieldResult) -> list[str]:
    return [
        cell(v)
        for v in (
            account_id,
            result.field,
            result.crm_value,
            result.proposed_value,
            result.winner,
            result.evidence_url,
            result.confidence,
            result.rationale,
        )
    ]


def _write_csv(path: Path, header: tuple[str, ...], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def _json_default(value: object) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def write_reports(
    results: list[AccountAudit | AccountError], out_dir: Path, meta: dict[str, Any]
) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    fixes, review, signals = [], [], []
    for result in results:
        if isinstance(result, AccountError):
            continue
        account_id = result.account.account_id
        for field in result.fields:
            if is_fix(field):
                fixes.append(_fix_row(account_id, field) + [""])
            elif needs_review(field):
                review.append(_fix_row(account_id, field))
        for signal in result.signals:
            signals.append(
                [
                    cell(v)
                    for v in (
                        account_id,
                        result.account.name,
                        signal.kind,
                        signal.detail,
                        signal.date,
                        signal.source,
                        signal.url,
                    )
                ]
            )
    audit = {
        **meta,
        "accounts": [
            {"error": r.error, "account": asdict(r.account)}
            if isinstance(r, AccountError)
            else asdict(r)
            for r in results
        ],
    }
    (out_dir / "audit.json").write_text(
        json.dumps(audit, indent=2, default=_json_default) + "\n", encoding="utf-8"
    )
    _write_csv(out_dir / "proposed_fixes.csv", (*FIX_COLUMNS, "approved"), fixes)
    _write_csv(out_dir / "needs_review.csv", FIX_COLUMNS, review)
    _write_csv(out_dir / "signals.csv", SIGNAL_COLUMNS, signals)
    errors = sum(isinstance(r, AccountError) for r in results)
    return {
        "accounts": len(results),
        "errors": errors,
        "fixes": len(fixes),
        "review": len(review),
        "signals": len(signals),
    }
