import concurrent.futures

import pytest

from agent.core.search_cache import clear_search_cache
from tools.search.multi_search import (
    MultiSearchOrchestrator,
    SearchProvider,
    SearchResult,
    SearchStrategy,
)
from tools.search.reliability import ProviderReliabilityManager, ReliabilityPolicy


class FlakyProvider(SearchProvider):
    def __init__(self, name: str, fail_times: int):
        super().__init__(name)
        self.fail_times = fail_times
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("temporary failure")
        return [
            SearchResult(
                title="Recovered",
                url="https://example.com/recovered",
                snippet="ok",
                score=0.8,
                provider=self.name,
            )
        ]


class _EmptyProvider(SearchProvider):
    def __init__(self, name: str):
        super().__init__(name=name, api_key="test")

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10):
        return []


class _FixedProvider(SearchProvider):
    def __init__(self, name: str, url: str = "https://example.com/a"):
        super().__init__(name=name, api_key="test")
        self._url = url

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 10):
        return [
            SearchResult(
                title="Result",
                url=self._url,
                snippet="snippet",
                content="",
                score=0.7,
                published_date="2026-02-01",
                provider=self.name,
            )
        ]


def test_reliability_manager_retries_until_success():
    manager = ProviderReliabilityManager(
        ReliabilityPolicy(
            max_retries=2,
            retry_backoff_seconds=0.0,
            circuit_breaker_failures=3,
            circuit_breaker_reset_seconds=60.0,
        )
    )

    attempts = {"n": 0}

    def flaky_call():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("temporary")
        return [1]

    result = manager.call("test-provider", flaky_call)

    assert result == [1]
    assert attempts["n"] == 3
    assert manager.is_open("test-provider") is False


def test_reliability_manager_opens_circuit_after_failures():
    manager = ProviderReliabilityManager(
        ReliabilityPolicy(
            max_retries=0,
            retry_backoff_seconds=0.0,
            circuit_breaker_failures=2,
            circuit_breaker_reset_seconds=60.0,
        )
    )

    attempts = {"n": 0}

    def always_fail():
        attempts["n"] += 1
        raise RuntimeError("down")

    assert manager.call("down-provider", always_fail) == []
    assert manager.call("down-provider", always_fail) == []
    assert manager.is_open("down-provider") is True

    calls_before_block = attempts["n"]
    assert manager.call("down-provider", always_fail) == []
    assert attempts["n"] == calls_before_block


def test_orchestrator_retries_transient_provider_errors():
    provider = FlakyProvider("tavily", fail_times=2)
    orchestrator = MultiSearchOrchestrator(
        providers=[provider],
        strategy=SearchStrategy.FALLBACK,
    )

    results = orchestrator.search(
        query="ai chips",
        max_results=2,
        strategy=SearchStrategy.FALLBACK,
    )

    assert provider.calls == 3
    assert len(results) == 1
    assert results[0].title == "Recovered"


def test_orchestrator_provider_profile_keeps_safe_fallback_when_selected_provider_empty():
    providers = [
        _EmptyProvider("semantic_scholar"),
        _FixedProvider("duckduckgo"),
    ]
    orchestrator = MultiSearchOrchestrator(
        providers=providers,
        strategy=SearchStrategy.FALLBACK,
    )

    clear_search_cache()
    results = orchestrator.search(
        query="test safe fallback",
        max_results=3,
        provider_profile=["semantic_scholar"],
    )

    assert results, "expected safe fallback provider to be tried when profile provider is empty"
    assert results[0].provider == "duckduckgo"


def test_orchestrator_retries_when_provider_records_error_and_returns_empty():
    """
    Providers often swallow exceptions and return [] while recording stats.error_count.
    The orchestrator should treat that as a failed attempt so the reliability manager
    can retry once before falling back.
    """

    class FlakyRecordedFailureProvider(SearchProvider):
        def __init__(self):
            super().__init__("flaky", api_key="test")
            self.calls = 0

        def is_available(self) -> bool:
            return True

        def search(self, query: str, max_results: int = 10):
            self.calls += 1
            if self.calls == 1:
                self.stats.record_failure("transient error")
                return []

            self.stats.record_success(latency_ms=1.0, quality=0.7)
            return [
                SearchResult(
                    title="OK",
                    url="https://example.com/ok",
                    snippet="ok",
                    score=0.7,
                    provider=self.name,
                )
            ]

    provider = FlakyRecordedFailureProvider()
    reliability = ProviderReliabilityManager(
        ReliabilityPolicy(
            max_retries=1,
            retry_backoff_seconds=0.0,
            circuit_breaker_failures=999,
            circuit_breaker_reset_seconds=0.0,
        )
    )
    orchestrator = MultiSearchOrchestrator(
        providers=[provider],
        strategy=SearchStrategy.FALLBACK,
        reliability_manager=reliability,
    )

    clear_search_cache()
    results = orchestrator.search(query="test reliability retry", max_results=5)

    assert results
    assert provider.calls == 2


def test_orchestrator_parallel_search_timeout_is_handled(monkeypatch):
    def fake_as_completed(_futures, timeout=None):
        raise concurrent.futures.TimeoutError()

    monkeypatch.setattr(concurrent.futures, "as_completed", fake_as_completed)

    orchestrator = MultiSearchOrchestrator(
        providers=[_FixedProvider("duckduckgo")],
        strategy=SearchStrategy.PARALLEL,
    )

    clear_search_cache()
    results = orchestrator.search(query="test parallel timeout", max_results=5)
    assert isinstance(results, list)
