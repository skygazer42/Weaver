import time

import tools.search.multi_search as multi_search_module
from agent.core.search_cache import SearchCache
from agent.workflows import deepsearch_optimized
from tools.search.multi_search import (
    MultiSearchOrchestrator,
    SearchProvider,
    SearchResult,
    SearchStrategy,
)


def test_deepsearch_query_cache_hits_before_ttl_expiry(monkeypatch):
    cache = SearchCache(max_size=10, ttl_seconds=60.0, similarity_threshold=1.0)
    calls = {"multi": 0}

    def fake_multi_search(query, max_results=10, strategy=None, provider_profile=None):
        calls["multi"] += 1
        return [
            {
                "title": "Cached",
                "url": "https://example.com/cached",
                "snippet": "cached snippet",
                "content": "cached content",
                "score": 0.8,
                "provider": "tavily",
            }
        ]

    monkeypatch.setattr(deepsearch_optimized, "get_search_cache", lambda: cache)
    monkeypatch.setattr(deepsearch_optimized, "multi_search", fake_multi_search)
    monkeypatch.setattr(deepsearch_optimized.settings, "search_strategy", "fallback", raising=False)

    r1 = deepsearch_optimized._search_query("ai chips", 3, config={})
    r2 = deepsearch_optimized._search_query("ai chips", 3, config={})

    assert calls["multi"] == 1
    assert r1[0]["url"] == r2[0]["url"]


def test_deepsearch_query_cache_refetches_after_ttl(monkeypatch):
    cache = SearchCache(max_size=10, ttl_seconds=0.01, similarity_threshold=1.0)
    calls = {"multi": 0}

    def fake_multi_search(query, max_results=10, strategy=None, provider_profile=None):
        calls["multi"] += 1
        return [
            {
                "title": "TTL",
                "url": "https://example.com/ttl",
                "snippet": "ttl snippet",
                "content": "ttl content",
                "score": 0.7,
                "provider": "tavily",
            }
        ]

    monkeypatch.setattr(deepsearch_optimized, "get_search_cache", lambda: cache)
    monkeypatch.setattr(deepsearch_optimized, "multi_search", fake_multi_search)
    monkeypatch.setattr(deepsearch_optimized.settings, "search_strategy", "fallback", raising=False)

    deepsearch_optimized._search_query("ai chips", 3, config={})
    time.sleep(0.02)
    deepsearch_optimized._search_query("ai chips", 3, config={})

    assert calls["multi"] == 2


class _DummyProvider(SearchProvider):
    def __init__(self):
        super().__init__("dummy")
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10):
        self.calls += 1
        return [
            SearchResult(
                title="Result",
                url="https://example.com/result",
                snippet="ok",
                score=0.6,
                provider=self.name,
            )
        ]


def test_multi_search_cache_respects_ttl(monkeypatch):
    provider = _DummyProvider()
    cache = SearchCache(max_size=10, ttl_seconds=0.01, similarity_threshold=1.0)

    monkeypatch.setattr(multi_search_module, "get_search_cache", lambda: cache)

    orchestrator = MultiSearchOrchestrator(
        providers=[provider],
        strategy=SearchStrategy.FALLBACK,
    )

    orchestrator.search("quantum chips", max_results=2, strategy=SearchStrategy.FALLBACK)
    orchestrator.search("quantum chips", max_results=2, strategy=SearchStrategy.FALLBACK)
    assert provider.calls == 1

    time.sleep(0.02)
    orchestrator.search("quantum chips", max_results=2, strategy=SearchStrategy.FALLBACK)
    assert provider.calls == 2
