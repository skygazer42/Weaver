from datetime import datetime, timedelta, timezone

from agent.workflows.query_strategy import (
    analyze_query_coverage,
    backfill_diverse_queries,
    is_time_sensitive_topic,
    summarize_freshness,
)


def test_backfill_diverse_queries_improves_dimension_coverage():
    queries = backfill_diverse_queries(
        topic="deep research agent",
        existing_queries=["deep research agent architecture"],
        historical_queries=[],
        query_num=5,
    )

    coverage = analyze_query_coverage(queries)

    assert len(queries) == 5
    assert coverage["score"] >= 0.8
    assert "official" in coverage["covered_dimensions"]
    assert "evidence" in coverage["covered_dimensions"]
    assert "risk" in coverage["covered_dimensions"]


def test_is_time_sensitive_topic_supports_english_and_chinese():
    assert is_time_sensitive_topic("latest ai policy updates") is True
    assert is_time_sensitive_topic("AI 最新进展") is True
    assert is_time_sensitive_topic("history of relational databases") is False


def test_summarize_freshness_computes_buckets_and_ratios():
    now = datetime.now(timezone.utc)

    search_runs = [
        {
            "query": "q1",
            "results": [
                {"url": "https://a.example/1", "published_date": (now - timedelta(days=2)).isoformat()},
                {"url": "https://a.example/2", "published_date": (now - timedelta(days=20)).isoformat()},
                {"url": "https://a.example/3", "published_date": (now - timedelta(days=220)).isoformat()},
                {"url": "https://a.example/4", "published_date": ""},
            ],
        }
    ]

    summary = summarize_freshness(search_runs)

    assert summary["total_results"] == 4
    assert summary["known_count"] == 3
    assert summary["unknown_count"] == 1
    assert summary["fresh_7_count"] == 1
    assert summary["fresh_30_count"] == 2
    assert summary["stale_180_count"] == 1
    assert summary["fresh_30_ratio"] == round(2 / 3, 3)
    assert summary["stale_180_ratio"] == round(1 / 3, 3)
