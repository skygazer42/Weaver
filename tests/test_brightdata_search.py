import pytest
import requests

from tools.search.providers import brightdata_search


class FakeResponse:
    def __init__(self, status_code, text="", json_data=None):
        self.status_code = status_code
        self._text = text
        self._json_data = json_data

    @property
    def text(self):
        return self._text

    def json(self):
        if self._json_data is not None:
            return self._json_data
        raise ValueError("no json")


def test_brightdata_search_returns_empty_when_no_key(monkeypatch):
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_api_key", ""
    )
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_serp_zone", "benchmark"
    )
    results = brightdata_search("pizza", max_results=5)
    assert results == []


def test_brightdata_search_returns_empty_when_no_zone(monkeypatch):
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_api_key",
        "a" * 10,
    )
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_serp_zone", ""
    )
    results = brightdata_search("pizza", max_results=5)
    assert results == []


def test_brightdata_search_throws_on_non_200(monkeypatch):
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_api_key",
        "a" * 10,
    )
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_serp_zone",
        "benchmark",
    )

    def _fake_post(*args, **kwargs):
        return FakeResponse(403, text="Forbidden")

    monkeypatch.setattr(requests, "post", _fake_post)

    with pytest.raises(RuntimeError, match="Bright Data API error"):
        brightdata_search("pizza", max_results=5)


def test_brightdata_search_throws_on_unparseable_200(monkeypatch):
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_api_key",
        "a" * 10,
    )
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_serp_zone",
        "benchmark",
    )

    def _fake_post(*args, **kwargs):
        return FakeResponse(200, text="not json", json_data=None)

    monkeypatch.setattr(requests, "post", _fake_post)

    with pytest.raises(RuntimeError, match="unparseable"):
        brightdata_search("pizza", max_results=5)


def test_brightdata_search_throws_on_missing_organic(monkeypatch):
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_api_key",
        "a" * 10,
    )
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_serp_zone",
        "benchmark",
    )

    def _fake_post(*args, **kwargs):
        return FakeResponse(200, json_data={"general": {}, "input": {}})

    monkeypatch.setattr(requests, "post", _fake_post)

    with pytest.raises(RuntimeError, match="missing 'organic'"):
        brightdata_search("pizza", max_results=5)


def test_brightdata_search_parses_organic_results(monkeypatch):
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_api_key",
        "a" * 10,
    )
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_serp_zone",
        "benchmark",
    )

    def _fake_post(*args, **kwargs):
        return FakeResponse(
            200,
            json_data={
                "general": {},
                "input": {},
                "organic": [
                    {
                        "title": "Best Pizza",
                        "link": "https://example.com/1",
                        "description": "The best pizza in town",
                        "global_rank": 1,
                    },
                    {
                        "title": "Pizza Place",
                        "link": "https://example.com/2",
                        "description": "Another great pizza",
                        "global_rank": 2,
                    },
                ],
            },
        )

    monkeypatch.setattr(requests, "post", _fake_post)

    results = brightdata_search("pizza", max_results=5)
    assert len(results) == 2
    assert results[0]["title"] == "Best Pizza"
    assert results[0]["url"] == "https://example.com/1"
    assert results[0]["snippet"] == "The best pizza in town"
    assert results[0]["source"] == "brightdata"
    assert results[0]["global_rank"] == 1


def test_brightdata_credential_is_redacted_from_error(monkeypatch):
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_api_key",
        "fakebrightdatakey12345",
    )
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_serp_zone",
        "benchmark",
    )

    def _fake_post(*args, **kwargs):
        return FakeResponse(
            403,
            text="Invalid: api_key=fakebrightdatakey12345 rejected",
        )

    monkeypatch.setattr(requests, "post", _fake_post)

    with pytest.raises(RuntimeError) as exc_info:
        brightdata_search("pizza", max_results=5)

    msg = str(exc_info.value)
    assert "fakebrightdatakey12345" not in msg


def test_brightdata_credential_is_redacted_from_unparseable_200(monkeypatch):
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_api_key",
        "fakebrightdatakey67890",
    )
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_serp_zone",
        "benchmark",
    )

    def _fake_post(*args, **kwargs):
        return FakeResponse(
            200,
            text="api_key=fakebrightdatakey67890 was used",
            json_data=None,
        )

    monkeypatch.setattr(requests, "post", _fake_post)

    with pytest.raises(RuntimeError) as exc_info:
        brightdata_search("pizza", max_results=5)

    msg = str(exc_info.value)
    assert "fakebrightdatakey67890" not in msg


def test_brightdata_zone_is_required(monkeypatch):
    """Deleting the zone guard makes this test fail."""
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_api_key",
        "a" * 10,
    )
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_serp_zone", ""
    )

    post_calls = []

    def _fake_post(*args, **kwargs):
        post_calls.append((args, kwargs))
        return FakeResponse(200, json_data={"organic": []})

    monkeypatch.setattr(requests, "post", _fake_post)

    results = brightdata_search("pizza", max_results=5)
    assert results == []
    assert len(post_calls) == 0, (
        "Zone guard failed: a request was made without a zone. "
        "Deleting the zone check in brightdata_search() makes this test fail."
    )


def test_brightdata_zone_is_required_invalid_api_key(monkeypatch):
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_api_key", "short"
    )
    monkeypatch.setattr(
        "tools.search.providers.settings.brightdata_serp_zone",
        "benchmark",
    )

    post_calls = []

    def _fake_post(*args, **kwargs):
        post_calls.append((args, kwargs))
        return FakeResponse(200, json_data={"organic": []})

    monkeypatch.setattr(requests, "post", _fake_post)

    results = brightdata_search("pizza", max_results=5)
    assert results == []
    assert len(post_calls) == 0
