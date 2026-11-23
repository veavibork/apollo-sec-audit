import calendar
import re
from datetime import date, timedelta

from crm_audit.matching import normalize_name
from crm_audit.models import SecCompany, Signal
from crm_audit.rules import Rules

EDGAR_SUFFIX = re.compile(r"\s*/\s*[A-Z]{1,3}\s*/?\s*$")


def fiscal_year_end(mmdd: str | None) -> str | None:
    """'1231' -> 'December 31'."""
    if mmdd is None or len(mmdd) != 4 or not mmdd.isascii() or not mmdd.isdigit():
        return None
    month, day = int(mmdd[:2]), int(mmdd[2:])
    if not 1 <= month <= 12 or not 1 <= day <= calendar.monthrange(2024, month)[1]:
        return None
    return f"{calendar.month_name[month]} {day}"


def _comparable(name: str, rules: Rules) -> str:
    """Name without EDGAR's state suffix ('NVIDIA CORP/CA', 'X INC /DE/'), normalized."""
    return normalize_name(EDGAR_SUFFIX.sub("", name), rules.name_match.strip_words)


def sec_signals(company: SecCompany, rules: Rules, as_of: date) -> tuple[Signal, ...]:
    signals = [Signal("legal_name", company.name, "sec", None, None)]
    fye = fiscal_year_end(company.fiscal_year_end)
    if fye is not None:
        signals.append(Signal("fiscal_year_end", fye, "sec", None, None))
    seen = {_comparable(company.name, rules)}
    for former in company.former_names:
        comparable = _comparable(former.name, rules)
        if comparable in seen:
            continue
        seen.add(comparable)
        until = f" (until {former.to_date.isoformat()})" if former.to_date else ""
        signals.append(Signal("former_name", f"{former.name}{until}", "sec", former.to_date, None))
    since = as_of - timedelta(days=rules.signal_lookback_days)
    events = [
        Signal(f"8-K {item}", rules.signal_items[item], "sec", filing.filing_date, filing.url)
        for filing in company.filings
        if filing.form in rules.signal_forms and since < filing.filing_date <= as_of
        for item in filing.items
        if item in rules.signal_items
    ]
    events.sort(key=lambda s: (s.date or date.min, s.kind), reverse=True)
    return (*signals, *events)
