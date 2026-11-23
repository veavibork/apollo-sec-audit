import pytest
import requests
import responses

from crm_audit.errors import SourceError
from crm_audit.fetch import get_json

URL = "https://example.test/data.json"


@responses.activate
def test_returns_parsed_json() -> None:
    responses.get(URL, json={"ok": True})
    assert get_json(requests.Session(), "src", URL, headers={}) == {"ok": True}


@responses.activate
def test_http_error_raises_source_error_without_headers() -> None:
    responses.get(URL, status=401, json={"error": "bad key"})
    with pytest.raises(SourceError) as exc:
        get_json(requests.Session(), "src", URL, headers={"x-api-key": "secret-key"})
    assert str(exc.value) == "src: HTTP 401"


@responses.activate
def test_invalid_json_raises_source_error() -> None:
    responses.get(URL, body="<html>oops</html>", status=200)
    with pytest.raises(SourceError, match="not valid JSON"):
        get_json(requests.Session(), "src", URL, headers={})


@responses.activate
def test_connection_error_raises_source_error() -> None:
    responses.get(URL, body=requests.ConnectionError("boom"))
    with pytest.raises(SourceError, match="request failed"):
        get_json(requests.Session(), "src", URL, headers={})
