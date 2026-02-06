from datetime import datetime, timedelta, timezone

from tools.search.multi_search import MultiSearchOrchestrator, SearchResult


def _days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_freshness_ranking_boosts_recent_results_for_time_sensitive_queries(monkeypatch):
    from common.config import settings

    monkeypatch.setattr(settings, "search_enable_freshness_ranking", True, raising=False)
    monkeypatch.setattr(settings, "search_freshness_half_life_days", 30.0, raising=False)
    monkeypatch.setattr(settings, "search_freshness_weight", 0.4, raising=False)

    orchestrator = MultiSearchOrchestrator(providers=[])
    results = [
        SearchResult(
            title="Older high-score",
            url="https://example.com/old",
            snippet="old",
            score=0.9,
            published_date=_days_ago(400),
            provider="test",
        ),
        SearchResult(
            title="Recent medium-score",
            url="https://example.com/new",
            snippet="new",
            score=0.6,
            published_date=_days_ago(1),
            provider="test",
        ),
    ]

    ranked = orchestrator._deduplicate_and_rank(results, max_results=2, query="latest ai news")

    assert ranked[0].url == "https://example.com/new"


def test_non_time_sensitive_queries_keep_relevance_priority(monkeypatch):
    from common.config import settings

    monkeypatch.setattr(settings, "search_enable_freshness_ranking", True, raising=False)
    monkeypatch.setattr(settings, "search_freshness_half_life_days", 30.0, raising=False)
    monkeypatch.setattr(settings, "search_freshness_weight", 0.4, raising=False)

    orchestrator = MultiSearchOrchestrator(providers=[])
    results = [
        SearchResult(
            title="Older high-score",
            url="https://example.com/old",
            snippet="old",
            score=0.9,
            published_date=_days_ago(400),
            provider="test",
        ),
        SearchResult(
            title="Recent medium-score",
            url="https://example.com/new",
            snippet="new",
            score=0.6,
            published_date=_days_ago(1),
            provider="test",
        ),
    ]

    ranked = orchestrator._deduplicate_and_rank(results, max_results=2, query="history of ai")

    assert ranked[0].url == "https://example.com/old"
