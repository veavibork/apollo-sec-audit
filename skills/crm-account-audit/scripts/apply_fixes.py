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
from crm_audit.console import safe_output
from crm_audit.reports import FIX_COLUMNS, cell, uncell
from crm_audit.rules import load_industries
from crm_audit.states import state_code

APPROVED = frozenset({"y", "yes"})
INDUSTRY_LABELS = frozenset(label for _, _, label in load_industries().ranges)
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
    if field == "industry" and value not in INDUSTRY_LABELS:
        raise ValueError(f"{value!r} is not a known industry label")
    return raw.strip()


def text(fix: dict[str, str], key: str) -> str:
    return (fix.get(key) or "").strip()


def fix_account_id(fix: dict[str, str]) -> str:
    return uncell(text(fix, "account_id")).strip()


def apply_one(
    fix: dict[str, str], by_id: dict[str, dict[str, str]], done: set[tuple[str, str]]
) -> tuple[bool, str]:
    account_id, field = fix_account_id(fix), text(fix, "field")
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
        outcomes.append(Outcome(line, fix_account_id(fix), text(fix, "field"), applied, reason))
    return outcomes


def row_value(value: object) -> str:
    return "(blank)" if value is None else cell(value)


def write_atomic(
    path: Path, header: list[str], rows: list[dict[str, str]], replace: bool = True
) -> None:
    """Write via a temp file. With replace=False, fail if the path exists by then."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        if replace:
            os.replace(tmp, path)
        else:
            os.link(tmp, path)
            Path(tmp).unlink()
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def ensure_unchanged(path: Path, original: bytes) -> None:
    if path.read_bytes() != original:
        raise ValueError(f"{path} changed while apply_fixes was running; nothing written")


def mark_approvals(fixes: list[dict[str, str]], pairs: list[str]) -> None:
    """Set approved=y on rows named 'ACCOUNT:FIELD'. ValueError if any pair can't be approved."""
    keys = {(fix_account_id(f), text(f, "field")): f for f in fixes}
    unknown, refused = [], []
    for pair in pairs:
        account_id, _, field = pair.rpartition(":")
        fix = keys.get((account_id.strip(), field.strip()))
        if fix is None:
            unknown.append(pair)
        elif text(fix, "approved") and text(fix, "approved").casefold() not in APPROVED:
            refused.append(f"{pair} (already marked {text(fix, 'approved')!r})")
        else:
            fix["approved"] = "y"
    if unknown:
        raise ValueError(f"--approve matches no proposed fix: {', '.join(unknown)}")
    if refused:
        raise ValueError(
            f"--approve would override a reviewer's entry: {', '.join(refused)}; "
            "clear it in the fixes file first"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=Path, default=Path("data/accounts.csv"))
    parser.add_argument("--fixes", type=Path, default=Path("reports/proposed_fixes.csv"))
    parser.add_argument("--out", type=Path, default=Path("data/accounts.updated.csv"))
    parser.add_argument(
        "--approve",
        action="append",
        default=[],
        metavar="ACCOUNT:FIELD",
        help="record approval of this row in the fixes file, then apply",
    )
    parser.add_argument("--force", action="store_true", help="replace an existing --out file")
    args = parser.parse_args(argv)
    safe_output()
    if args.out.resolve() == args.accounts.resolve():
        print("error: --out must differ from --accounts", file=sys.stderr)
        return 1
    if args.out.exists() and not args.force:
        print(
            f"error: {args.out} already exists and may hold an earlier round's fixes. "
            "For another round, pass --accounts with that file and a new --out; "
            "pass --force to replace it.",
            file=sys.stderr,
        )
        return 1
    try:
        load_accounts(args.accounts)
        header, rows = read_rows(args.accounts)
        fixes_bytes = args.fixes.read_bytes()
        with args.fixes.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fix_header = list(reader.fieldnames or [])
            if not {*FIX_COLUMNS, "approved"} <= set(fix_header):
                raise ValueError(f"{args.fixes}: missing columns; expected the audit's format")
            fixes = list(reader)
        for line, fix in enumerate(fixes, start=2):
            if None in fix:
                raise ValueError(f"{args.fixes} line {line}: more values than columns")
        if args.approve:
            mark_approvals(fixes, args.approve)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    outcomes = apply(rows, fixes)
    try:
        ensure_unchanged(args.fixes, fixes_bytes)
        write_atomic(args.out, header, rows, replace=args.force)
        if args.approve:
            ensure_unchanged(args.fixes, fixes_bytes)
            write_atomic(args.fixes, fix_header, fixes)
    except FileExistsError:
        print(f"error: {args.out} appeared during the run; nothing written", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    applied = [o for o in outcomes if o.applied]
    print(f"Wrote {args.out}: {len(applied)} applied, {len(outcomes) - len(applied)} skipped.")
    for o in outcomes:
        status = "applied" if o.applied else "SKIPPED"
        print(f"  line {o.line} {o.account_id} {status}: {o.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
