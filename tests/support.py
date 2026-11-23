import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"
HUBS_CIK = "0001404655"
USER_AGENT = "Test Runner test@example.com"


def load_fixture(rel: str) -> Any:
    return json.loads((FIXTURES / rel).read_text(encoding="utf-8"))
