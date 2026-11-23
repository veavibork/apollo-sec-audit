import pytest

from crm_audit.cache import JsonCache
from crm_audit.errors import SourceError


def test_round_trip(cache: JsonCache) -> None:
    cache.put("apollo/a.com.json", {"x": 1})
    assert cache.get("apollo/a.com.json") == {"x": 1}


def test_miss_returns_none(cache: JsonCache) -> None:
    assert cache.get("sec/company_tickers.json") is None


@pytest.mark.parametrize(
    "key",
    [
        "../x.json",
        "apollo/../../x.json",
        "apollo/a/b.json",
        "other/a.json",
        "apollo/.json",
        "a.json",
    ],
)
def test_rejects_keys_outside_cache(cache: JsonCache, key: str) -> None:
    with pytest.raises(ValueError, match="invalid cache key"):
        cache.path(key)


def test_corrupt_file_raises_instead_of_refetching(cache: JsonCache) -> None:
    path = cache.path("apollo/a.com.json")
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SourceError, match="corrupt cache file"):
        cache.get("apollo/a.com.json")


def test_put_leaves_no_temp_files(cache: JsonCache) -> None:
    cache.put("sec/x.json", [1, 2])
    assert [p.name for p in cache.path("sec/x.json").parent.iterdir()] == ["x.json"]


def test_failed_put_leaves_no_file(cache: JsonCache) -> None:
    with pytest.raises(TypeError):
        cache.put("sec/x.json", {"bad": object()})
    assert list(cache.path("sec/x.json").parent.iterdir()) == []


@pytest.mark.parametrize("key", ["apollo/con.com.json", "apollo/NUL.org.json", "sec/com1.json"])
def test_rejects_windows_reserved_names(cache: JsonCache, key: str) -> None:
    with pytest.raises(ValueError, match="invalid cache key"):
        cache.path(key)


def test_cached_null_raises_as_corrupt(cache: JsonCache) -> None:
    path = cache.path("apollo/a.com.json")
    path.parent.mkdir(parents=True)
    path.write_text("null", encoding="utf-8")
    with pytest.raises(SourceError, match="corrupt cache file"):
        cache.get("apollo/a.com.json")
