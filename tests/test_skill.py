import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "crm-account-audit"
SKILL = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")


def frontmatter() -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", SKILL, re.S)
    assert match, "SKILL.md must start with YAML frontmatter"
    pairs = (line.split(":", 1) for line in match.group(1).splitlines())
    return {key.strip(): value.strip() for key, value in pairs}


def test_frontmatter_name_and_description() -> None:
    meta = frontmatter()
    assert set(meta) == {"name", "description"}
    assert meta["name"] == SKILL_DIR.name
    assert re.fullmatch(r"[a-z0-9-]{1,64}", meta["name"])
    assert 0 < len(meta["description"]) <= 1024


def test_every_referenced_script_exists() -> None:
    scripts = set(re.findall(r"skills/crm-account-audit/(scripts/\w+\.py)", SKILL))
    assert scripts == {"scripts/audit.py", "scripts/summary.py", "scripts/apply_fixes.py"}
    for script in scripts:
        assert (SKILL_DIR / script).is_file(), script


def test_files_section_matches_disk() -> None:
    listed = set(re.findall(r"- `(scripts/[\w.]+)`", SKILL))
    assert listed
    for path in listed:
        assert (SKILL_DIR / path).is_file(), path


def test_skill_explains_every_sec_status() -> None:
    for status in (
        "matched",
        "no_ticker",
        "ticker_not_in_sec",
        "name_check_failed",
        "no_apollo_org",
    ):
        assert f"`{status}`" in SKILL, status


def test_skill_says_to_use_precomputed_counts() -> None:
    assert "event_counts" in SKILL


def test_skill_says_matched_includes_borderline() -> None:
    line = next(x for x in SKILL.splitlines() if x.startswith("- `matched`"))
    assert "borderline" in line
