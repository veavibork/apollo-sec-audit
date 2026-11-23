from pathlib import Path

import pytest

from crm_audit.cache import JsonCache


@pytest.fixture
def cache(tmp_path: Path) -> JsonCache:
    return JsonCache(tmp_path / "cache")
