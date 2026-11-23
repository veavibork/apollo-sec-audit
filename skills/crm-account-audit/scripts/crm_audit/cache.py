import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from crm_audit.errors import SourceError

KEY_PATTERN = re.compile(r"^(apollo|sec)/[A-Za-z0-9][A-Za-z0-9._-]*\.json$")
WINDOWS_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{p}{n}" for p in ("com", "lpt") for n in range(10)
}


class JsonCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, key: str) -> Path:
        stem = key.split("/", 1)[-1].split(".", 1)[0].lower()
        if not KEY_PATTERN.fullmatch(key) or ".." in key or stem in WINDOWS_RESERVED:
            raise ValueError(f"invalid cache key: {key!r}")
        return self.root / key

    def get(self, key: str) -> Any | None:
        path = self.path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_bytes())
        except ValueError:
            data = None
        if data is None:
            raise SourceError(f"corrupt cache file {path}; delete it to refetch")
        return data

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
