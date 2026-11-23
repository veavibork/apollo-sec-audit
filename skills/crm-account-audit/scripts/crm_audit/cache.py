import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from crm_audit.errors import SourceError

KEY_PATTERN = re.compile(r"^(apollo|sec)/[A-Za-z0-9][A-Za-z0-9._-]*\.json$")


class JsonCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, key: str) -> Path:
        if not KEY_PATTERN.fullmatch(key) or ".." in key:
            raise ValueError(f"invalid cache key: {key!r}")
        return self.root / key

    def get(self, key: str) -> Any | None:
        path = self.path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_bytes())
        except ValueError as exc:
            raise SourceError(f"corrupt cache file {path}; delete it to refetch") from exc

    def put(self, key: str, data: Any) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
