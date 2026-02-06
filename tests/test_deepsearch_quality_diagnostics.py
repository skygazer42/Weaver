from datetime import datetime, timedelta, timezone

from agent.workflows import deepsearch_optimized


def _patch_basics(monkeypatch, search_results):
    monkeypatch.setattr(deepsearch_optimized, "_model_for_task", lambda task, config: "fake-model")
    monkeypatch.setattr(deepsearch_optimized, "_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(deepsearch_optimized, "_resolve_provider_profile", lambda state: None)
    monkeypatch.setattr(deepsearch_optimized, "_generate_queries", lambda *args, **kwargs: [args[1]])
    monkeypatch.setattr(deepsearch_optimized, "_search_query", lambda *args, **kwargs: search_results)
    monkeypatch.setattr(
        deepsearch_optimized,
        "_pick_relevant_urls",
        lambda *args, **kwargs: [r["url"] for r in search_results[:3]],
    )
    monkeypatch.setattr(
        deepsearch_optimized,
        "_summarize_new_knowledge",
        lambda *args, **kwargs: (True, "summary"),
    )
    monkeypatch.setattr(deepsearch_optimized, "_final_report", lambda *args, **kwargs: "final report")
    monkeypatch.setattr(deepsearch_optimized, "_save_deepsearch_data", lambda *args, **kwargs: "")

    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_enable_crawler", False, raising=False)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_use_gap_analysis", False, raising=False)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_max_epochs", 2, raising=False)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_query_num", 1, raising=False)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_results_per_query", 3, raising=False)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_max_tokens", 0, raising=False)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_max_seconds", 0.0, raising=False)


def test_quality_summary_exposes_query_and_freshness_diagnostics(monkeypatch):
    now = datetime.now(timezone.utc)
    search_results = [
        {
            "title": "Recent",
            "url": "https://example.com/recent",
            "summary": "recent",
            "score": 0.8,
            "published_date": (now - timedelta(days=3)).isoformat(),
        },
        {
            "title": "Old",
            "url": "https://example.com/old",
            "summary": "old",
            "score": 0.6,
            "published_date": (now - timedelta(days=90)).isoformat(),
        },
        {
            "title": "Unknown",
            "url": "https://example.com/unknown",
            "summary": "unknown",
            "score": 0.5,
        },
    ]

    _patch_basics(monkeypatch, search_results)

    result = deepsearch_optimized.run_deepsearch_optimized(
        {"input": "enterprise knowledge management"},
        config={},
    )

    quality = result["quality_summary"]

    assert "query_coverage_score" in quality
    assert "query_dimensions_covered" in quality
    assert "freshness_summary" in quality
    assert quality["freshness_summary"]["total_results"] == 3
    assert quality["freshness_warning"] == ""
    assert result["deepsearch_artifacts"]["query_coverage"]["score"] == quality["query_coverage_score"]


def test_time_sensitive_topics_trigger_low_freshness_warning(monkeypatch):
    now = datetime.now(timezone.utc)
    search_results = [
        {
            "title": "Old1",
            "url": "https://example.com/old1",
            "summary": "old1",
            "score": 0.8,
            "published_date": (now - timedelta(days=320)).isoformat(),
        },
        {
            "title": "Old2",
            "url": "https://example.com/old2",
            "summary": "old2",
            "score": 0.7,
            "published_date": (now - timedelta(days=480)).isoformat(),
        },
        {
            "title": "Old3",
            "url": "https://example.com/old3",
            "summary": "old3",
            "score": 0.65,
            "published_date": (now - timedelta(days=220)).isoformat(),
        },
    ]

    _patch_basics(monkeypatch, search_results)

    result = deepsearch_optimized.run_deepsearch_optimized(
        {"input": "latest ai regulation updates"},
        config={},
    )

    quality = result["quality_summary"]
    messages = result["messages"]

    assert quality["time_sensitive_query"] is True
    assert quality["freshness_summary"]["known_count"] == 3
    assert quality["freshness_warning"] == "low_freshness_for_time_sensitive_query"
    assert any("新鲜来源占比较低" in (msg.content or "") for msg in messages)
