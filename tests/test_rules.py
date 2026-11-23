import copy
import tomllib
from typing import Any

import pytest

from crm_audit.rules import RULES_PATH, load_industries, load_rules, parse_rules
from support import load_fixture


def raw_rules() -> dict[str, Any]:
    with RULES_PATH.open("rb") as f:
        return tomllib.load(f)


def test_default_rules_load() -> None:
    rules = load_rules()
    assert rules.precedence["annual_revenue"] == ("sec", "apollo")
    assert rules.precedence["employees"] == ("apollo",)
    assert rules.tolerance == {"annual_revenue": 0.15, "employees": 0.15}
    assert (rules.name_match.pass_score, rules.name_match.borderline_score) == (90, 70)
    assert rules.review_on_conflict == {"industry"}
    assert set(rules.signal_items) == {"5.02", "2.01", "2.05", "1.01"}
    assert rules.signal_lookback_days == 365


def _broken(path: list[str], value: Any) -> dict[str, Any]:
    data = copy.deepcopy(raw_rules())
    target = data
    for key in path[:-1]:
        target = target[key]
    if value is None:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return data


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (["precedence", "annual_revenue"], ["sec", "crm"]),
        (["precedence", "employees"], None),
        (["precedence", "founded"], ["apollo"]),
        (["tolerance", "annual_revenue"], 1.5),
        (["tolerance", "annual_revenue"], True),
        (["name_match", "borderline"], 95),
        (["name_match", "strip_words"], "inc"),
        (["signals", "lookback_days"], 0),
        (["review_on_conflict", "fields"], ["revenue"]),
        (["sec"], None),
    ],
)
def test_invalid_rules_are_rejected(path: list[str], value: Any) -> None:
    with pytest.raises(ValueError, match="rules:"):
        parse_rules(_broken(path, value))


def test_every_sec_sic_code_maps_to_an_industry() -> None:
    industries = load_industries()
    codes = load_fixture("sec/sic_codes.json")
    unmapped = [code for code in codes if industries.label(code) is None]
    assert unmapped == []


@pytest.mark.parametrize(
    ("sic", "label"),
    [
        ("7372", "Software"),
        ("7370", "Software"),
        ("3674", "Semiconductors"),
        ("3571", "Computer Hardware"),
        ("2834", "Pharmaceuticals"),
        ("1311", "Oil & Gas"),
        ("2911", "Oil & Gas"),
        ("6021", "Banking"),
        ("6331", "Insurance"),
        ("6798", "Real Estate"),
        ("5812", "Restaurants"),
        ("5961", "Retail"),
        ("4841", "Media & Entertainment"),
        ("4813", "Telecommunications"),
        ("3841", "Medical Devices"),
        ("3711", "Automotive"),
        ("0100", "Agriculture"),
    ],
)
def test_industry_labels(sic: str, label: str) -> None:
    assert load_industries().label(sic) == label


@pytest.mark.parametrize("sic", [None, "", "abc", "７３７２", "-1"])
def test_industry_label_rejects_non_codes(sic: str | None) -> None:
    assert load_industries().label(sic) is None


@pytest.mark.parametrize(
    "path",
    [["precedence", "annual_revenue"], ["sec", "revenue_concepts"], ["signals", "forms"]],
)
def test_empty_required_lists_are_rejected(path: list[str]) -> None:
    with pytest.raises(ValueError, match="rules:"):
        parse_rules(_broken(path, []))


@pytest.mark.parametrize("path", [["review_on_conflict", "fields"], ["name_match", "strip_words"]])
def test_optional_lists_may_be_empty(path: list[str]) -> None:
    parse_rules(_broken(path, []))


def test_overlapping_ranges_of_equal_width_are_rejected(tmp_path: Any) -> None:
    path = tmp_path / "sic.csv"
    path.write_text(
        "sic_start,sic_end,label\n7370,7379,Software\n7370,7379,Technology\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="sic_industry: overlapping"):
        load_industries(path)
