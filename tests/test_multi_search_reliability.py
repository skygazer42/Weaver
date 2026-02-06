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
