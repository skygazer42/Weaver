import pytest

from tools.search import fallback_search


def test_run_fallback_search_applies_alias_mapping(monkeypatch):
    monkeypatch.setitem(
        fallback_search._ENGINE_HANDLERS,
        "google_cse",
        lambda *, query, max_results: [{"url": "https://example.com"}],
    )

    engine, results = fallback_search.run_fallback_search(
        query="hello", max_results=5, engines=["google"]
    )

    assert engine == "google_cse"
    assert results and results[0]["url"] == "https://example.com"


def test_run_fallback_search_skips_unknown_engines(monkeypatch):
    monkeypatch.setitem(
        fallback_search._ENGINE_HANDLERS,
        "tavily",
        lambda *, query, max_results: [{"url": "https://tavily.example"}],
    )

    engine, results = fallback_search.run_fallback_search(
        query="hello", max_results=5, engines=["does_not_exist", "tavily"]
    )

    assert engine == "tavily"
    assert results and results[0]["url"] == "https://tavily.example"


def test_run_fallback_search_uses_first_engine_with_results(monkeypatch):
    monkeypatch.setitem(
        fallback_search._ENGINE_HANDLERS,
        "serper",
        lambda *, query, max_results: [],
    )
    monkeypatch.setitem(
        fallback_search._ENGINE_HANDLERS,
        "tavily",
        lambda *, query, max_results: [{"url": "https://tavily.example"}],
    )

    engine, _ = fallback_search.run_fallback_search(
        query="hello", max_results=5, engines=["serper", "tavily"]
    )

    assert engine == "tavily"


def test_run_fallback_search_continues_after_engine_error(monkeypatch):
    def _boom(*, query, max_results):
        raise RuntimeError("boom")

    monkeypatch.setitem(fallback_search._ENGINE_HANDLERS, "serper", _boom)
    monkeypatch.setitem(
        fallback_search._ENGINE_HANDLERS,
        "tavily",
        lambda *, query, max_results: [{"url": "https://tavily.example"}],
    )

    engine, results = fallback_search.run_fallback_search(
        query="hello", max_results=5, engines=["serper", "tavily"]
    )

    assert engine == "tavily"
    assert results and results[0]["url"] == "https://tavily.example"
