import csv
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
RULES_PATH = SCRIPTS_DIR / "rules.toml"
INDUSTRY_PATH = SCRIPTS_DIR / "sic_industry.csv"
SOURCES = frozenset({"sec", "apollo"})
FIELDS = frozenset({"annual_revenue", "hq_state", "industry", "employees"})


@dataclass(frozen=True)
class NameMatchRules:
    pass_score: float
    borderline_score: float
    strip_words: frozenset[str]


@dataclass(frozen=True)
class Rules:
    precedence: dict[str, tuple[str, ...]]
    tolerance: dict[str, float]
    review_on_conflict: frozenset[str]
    name_match: NameMatchRules
    revenue_concepts: tuple[str, ...]
    signal_lookback_days: int
    signal_forms: frozenset[str]
    signal_items: dict[str, str]


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"rules: [{key}] is missing")
    return value


def _str_list(value: Any, where: str, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"rules: {where} must be a list of strings")
    if not value and not allow_empty:
        raise ValueError(f"rules: {where} must not be empty")
    return tuple(value)


def _number(value: Any, where: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not low <= value <= high:
        raise ValueError(f"rules: {where} must be a number from {low} to {high}")
    return float(value)


def parse_rules(data: dict[str, Any]) -> Rules:
    precedence = {}
    for field, sources in _table(data, "precedence").items():
        order = _str_list(sources, f"precedence.{field}")
        if field not in FIELDS or not set(order) <= SOURCES:
            raise ValueError(f"rules: precedence.{field} is not a known field or source")
        precedence[field] = order
    if set(precedence) != FIELDS:
        raise ValueError(f"rules: precedence must cover {sorted(FIELDS)}")

    tolerance = {
        f: _number(v, f"tolerance.{f}", 0, 1) for f, v in _table(data, "tolerance").items()
    }
    if set(tolerance) != {"annual_revenue", "employees"}:
        raise ValueError("rules: tolerance must cover annual_revenue and employees")

    review = frozenset(
        _str_list(_table(data, "review_on_conflict").get("fields"), "review_on_conflict", True)
    )
    if not review <= FIELDS:
        raise ValueError("rules: review_on_conflict.fields has an unknown field")

    names = _table(data, "name_match")
    pass_score = _number(names.get("pass"), "name_match.pass", 0, 100)
    borderline = _number(names.get("borderline"), "name_match.borderline", 0, 100)
    if borderline > pass_score:
        raise ValueError("rules: name_match.borderline must not exceed name_match.pass")
    strip = frozenset(
        w.casefold() for w in _str_list(names.get("strip_words"), "strip_words", True)
    )

    signals = _table(data, "signals")
    lookback = signals.get("lookback_days")
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 1:
        raise ValueError("rules: signals.lookback_days must be a positive integer")
    items = _table(signals, "items")
    if not all(isinstance(v, str) and v for v in items.values()):
        raise ValueError("rules: signals.items values must be labels")

    return Rules(
        precedence=precedence,
        tolerance=tolerance,
        review_on_conflict=review,
        name_match=NameMatchRules(pass_score, borderline, strip),
        revenue_concepts=_str_list(_table(data, "sec").get("revenue_concepts"), "revenue_concepts"),
        signal_lookback_days=lookback,
        signal_forms=frozenset(_str_list(signals.get("forms"), "signals.forms")),
        signal_items=dict(items),
    )


def load_rules(path: Path = RULES_PATH) -> Rules:
    with path.open("rb") as f:
        return parse_rules(tomllib.load(f))


@dataclass(frozen=True)
class IndustryMap:
    ranges: tuple[tuple[int, int, str], ...]

    def label(self, sic: str | None) -> str | None:
        """Label of the narrowest SIC range that holds the code."""
        if sic is None or not sic.isascii() or not sic.isdigit():
            return None
        code = int(sic)
        hits = [(end - start, label) for start, end, label in self.ranges if start <= code <= end]
        return min(hits)[1] if hits else None


def load_industries(path: Path = INDUSTRY_PATH) -> IndustryMap:
    ranges: list[tuple[int, int, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            start, end, label = int(row["sic_start"]), int(row["sic_end"]), row["label"].strip()
            if start > end or not label:
                raise ValueError(f"sic_industry: bad row {row}")
            for other_start, other_end, other_label in ranges:
                overlaps = start <= other_end and other_start <= end
                if overlaps and end - start == other_end - other_start:
                    raise ValueError(
                        f"sic_industry: overlapping ranges of equal width: {label}, {other_label}"
                    )
            ranges.append((start, end, label))
    return IndustryMap(tuple(ranges))
