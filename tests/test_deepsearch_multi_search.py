import pytest

from agent.workflows import deepsearch, deepsearch_optimized


@pytest.mark.parametrize("module", [deepsearch, deepsearch_optimized])
def test_search_query_prefers_multi_search(module, monkeypatch):
    calls = {"multi": 0, "tavily": 0}

    def fake_multi_search(query, max_results=10, strategy=None):
        calls["multi"] += 1
        return [
            {
                "title": "Result",
                "url": "https://example.com/a",
                "snippet": "snippet text",
                "content": "full content",
                "score": 0.72,
                "published_date": "2026-02-05",
                "provider": "duckduckgo",
            }
        ]

    class FakeTavily:
        @staticmethod
        def invoke(payload, config=None):
            calls["tavily"] += 1
            raise AssertionError("tavily fallback should not be used when multi_search succeeds")

    monkeypatch.setattr(module, "multi_search", fake_multi_search)
    monkeypatch.setattr(module, "tavily_search", FakeTavily())
    monkeypatch.setattr(module.settings, "search_strategy", "fallback")

    results = module._search_query("latest ai news", 5, {})

    assert calls["multi"] == 1
    assert calls["tavily"] == 0
    assert len(results) == 1
    assert results[0]["summary"] == "snippet text"
    assert results[0]["raw_excerpt"] == "full content"


@pytest.mark.parametrize("module", [deepsearch, deepsearch_optimized])
def test_search_query_falls_back_to_tavily_on_multi_search_error(module, monkeypatch):
    calls = {"multi": 0, "tavily": 0}

    def fake_multi_search(query, max_results=10, strategy=None):
        calls["multi"] += 1
        raise RuntimeError("search backend unavailable")

    class FakeTavily:
        @staticmethod
        def invoke(payload, config=None):
            calls["tavily"] += 1
            return [
                {
                    "title": "Tavily Result",
                    "url": "https://example.com/b",
                    "summary": "fallback summary",
                    "raw_excerpt": "fallback content",
                    "score": 0.55,
                }
            ]

    monkeypatch.setattr(module, "multi_search", fake_multi_search)
    monkeypatch.setattr(module, "tavily_search", FakeTavily())
    monkeypatch.setattr(module.settings, "search_strategy", "fallback")

    results = module._search_query("ai chips", 3, {})

    assert calls["multi"] == 1
    assert calls["tavily"] == 1
    assert len(results) == 1
    assert results[0]["summary"] == "fallback summary"
