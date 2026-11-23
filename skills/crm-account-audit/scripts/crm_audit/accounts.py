import csv
import math
from pathlib import Path

from crm_audit.models import Account

COLUMNS = ("account_id", "name", "domain", "annual_revenue", "hq_state", "industry", "employees")
EDITABLE = ("annual_revenue", "hq_state", "industry", "employees")


def parse_text(raw: str | None) -> str | None:
    text = (raw or "").strip()
    return text or None


def parse_revenue(raw: str | None) -> float | None:
    text = parse_text(raw)
    if text is None:
        return None
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"annual_revenue {text!r} is not a number") from None
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"annual_revenue {text!r} must be a non-negative number")
    return value


def parse_employees(raw: str | None) -> int | None:
    text = parse_text(raw)
    if text is None:
        return None
    if not text.isascii() or not text.isdigit():
        raise ValueError(f"employees {text!r} must be a whole number")
    return int(text)


def parse_row(row: dict[str, str]) -> Account:
    account_id = parse_text(row.get("account_id"))
    if account_id is None:
        raise ValueError("account_id is blank")
    return Account(
        account_id=account_id,
        name=parse_text(row.get("name")),
        domain=parse_text(row.get("domain")),
        annual_revenue=parse_revenue(row.get("annual_revenue")),
        hq_state=parse_text(row.get("hq_state")),
        industry=parse_text(row.get("industry")),
        employees=parse_employees(row.get("employees")),
    )


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        if sorted(header) != sorted(COLUMNS):
            raise ValueError(f"{path}: columns must be {', '.join(COLUMNS)}")
        rows = list(reader)
    for line, row in enumerate(rows, start=2):
        if None in row:
            raise ValueError(f"{path} line {line}: more values than columns")
    return header, rows


def load_accounts(path: Path) -> list[Account]:
    _, rows = read_rows(path)
    accounts: list[Account] = []
    seen: set[str] = set()
    for line, row in enumerate(rows, start=2):
        try:
            account = parse_row(row)
        except ValueError as exc:
            raise ValueError(f"{path} line {line}: {exc}") from None
        if account.account_id in seen:
            raise ValueError(f"{path} line {line}: duplicate account_id {account.account_id}")
        seen.add(account.account_id)
        accounts.append(account)
    return accounts
