"""Apply approved rows from proposed_fixes.csv to a copy of the accounts CSV."""

import argparse
import csv
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from crm_audit.accounts import (
    EDITABLE,
    load_accounts,
    parse_employees,
    parse_revenue,
    parse_text,
    read_rows,
)
from crm_audit.reports import FIX_COLUMNS, cell, uncell
from crm_audit.states import state_code

APPROVED = frozenset({"y", "yes"})
PARSERS = {
    "annual_revenue": parse_revenue,
    "employees": parse_employees,
    "hq_state": parse_text,
    "industry": parse_text,
}


@dataclass(frozen=True)
class Outcome:
    line: int
    account_id: str
    field: str
    applied: bool
    reason: str


def check_proposed(field: str, raw: str) -> str:
    """The value to write, or ValueError if it isn't valid for the field."""
    value = PARSERS[field](raw)
    if value is None:
        raise ValueError("proposed value is blank")
    if field == "hq_state" and state_code(str(value)) != value:
        raise ValueError(f"{value!r} is not a two-letter US state code")
    if field == "industry" and " | " in str(value):
        raise ValueError("proposed industry lists several labels; pick one in the CRM")
    return raw.strip()


def text(fix: dict[str, str], key: str) -> str:
    return (fix.get(key) or "").strip()


def apply_one(
    fix: dict[str, str], by_id: dict[str, dict[str, str]], done: set[tuple[str, str]]
) -> tuple[bool, str]:
    account_id, field = text(fix, "account_id"), text(fix, "field")
    row = by_id.get(account_id)
    if row is None:
        return False, "account not in the accounts file"
    if field not in EDITABLE:
        return False, f"field {field!r} can't be edited"
    if (account_id, field) in done:
        return False, "already changed by an earlier approved row"
    try:
        current = PARSERS[field](row[field])
        expected = PARSERS[field](uncell(fix.get("current_value") or ""))
        value = check_proposed(field, uncell(fix.get("proposed_value") or ""))
    except ValueError as exc:
        return False, str(exc)
    if current != expected:
        return False, "CRM value changed since the audit; rerun the audit"
    row[field] = value
    done.add((account_id, field))
    return True, f"{field}: {row_value(current)} -> {value}"


def apply(rows: list[dict[str, str]], fixes: list[dict[str, str]]) -> list[Outcome]:
    by_id = {row["account_id"].strip(): row for row in rows}
    done: set[tuple[str, str]] = set()
    outcomes = []
    for line, fix in enumerate(fixes, start=2):
        if text(fix, "approved").casefold() not in APPROVED:
            continue
        applied, reason = apply_one(fix, by_id, done)
        outcomes.append(Outcome(line, text(fix, "account_id"), text(fix, "field"), applied, reason))
    return outcomes


def row_value(value: object) -> str:
    return "(blank)" if value is None else cell(value)


def write_atomic(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=Path, default=Path("data/accounts.csv"))
    parser.add_argument("--fixes", type=Path, default=Path("reports/proposed_fixes.csv"))
    parser.add_argument("--out", type=Path, default=Path("data/accounts.updated.csv"))
    args = parser.parse_args(argv)
    if args.out.resolve() == args.accounts.resolve():
        print("error: --out must differ from --accounts", file=sys.stderr)
        return 1
    try:
        load_accounts(args.accounts)
        header, rows = read_rows(args.accounts)
        with args.fixes.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not {*FIX_COLUMNS, "approved"} <= set(reader.fieldnames or []):
                raise ValueError(f"{args.fixes}: missing columns; expected the audit's format")
            fixes = list(reader)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    outcomes = apply(rows, fixes)
    write_atomic(args.out, header, rows)

    applied = [o for o in outcomes if o.applied]
    print(f"Wrote {args.out}: {len(applied)} applied, {len(outcomes) - len(applied)} skipped.")
    for o in outcomes:
        status = "applied" if o.applied else "SKIPPED"
        print(f"  line {o.line} {o.account_id} {status}: {o.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
