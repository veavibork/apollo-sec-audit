from typing import Any

import requests

from crm_audit.errors import SourceError

TIMEOUT_SECONDS = 30


def get_json(
    session: requests.Session,
    source: str,
    url: str,
    *,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
) -> Any:
    """GET a URL and return parsed JSON. Redirects are errors. Errors never include headers."""
    try:
        resp = session.get(
            url, headers=headers, params=params, timeout=TIMEOUT_SECONDS, allow_redirects=False
        )
    except requests.RequestException as exc:
        raise SourceError(f"{source}: request failed ({type(exc).__name__})") from None
    if not 200 <= resp.status_code < 300:
        raise SourceError(f"{source}: HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError:
        raise SourceError(f"{source}: response is not valid JSON") from None
