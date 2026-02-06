import time

from agent.workflows import deepsearch_optimized


def _patch_deepsearch_basics(monkeypatch):
    monkeypatch.setattr(deepsearch_optimized, "_model_for_task", lambda task, config: "fake-model")
    monkeypatch.setattr(deepsearch_optimized, "_chat_model", lambda *args, **kwargs: object())
    monkeypatch.setattr(deepsearch_optimized, "_resolve_provider_profile", lambda state: None)
    monkeypatch.setattr(deepsearch_optimized, "_pick_relevant_urls", lambda *args, **kwargs: [])
    monkeypatch.setattr(deepsearch_optimized, "_summarize_new_knowledge", lambda *args, **kwargs: (False, ""))
    monkeypatch.setattr(deepsearch_optimized, "_final_report", lambda *args, **kwargs: "final report")
    monkeypatch.setattr(deepsearch_optimized, "_save_deepsearch_data", lambda *args, **kwargs: "")
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_enable_crawler", False, raising=False)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_use_gap_analysis", False, raising=False)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_max_epochs", 2, raising=False)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_query_num", 1, raising=False)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_results_per_query", 1, raising=False)


def test_deepsearch_stops_when_token_budget_exceeded(monkeypatch):
    _patch_deepsearch_basics(monkeypatch)
    calls = {"search": 0}

    monkeypatch.setattr(
        deepsearch_optimized,
        "_generate_queries",
        lambda *args, **kwargs: ["a very long query that should consume token budget quickly"],
    )

    def fake_search(*args, **kwargs):
        calls["search"] += 1
        return []

    monkeypatch.setattr(deepsearch_optimized, "_search_query", fake_search)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_max_tokens", 3, raising=False)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_max_seconds", 0.0, raising=False)

    result = deepsearch_optimized.run_deepsearch_optimized({"input": "AI"}, config={})

    assert result["budget_stop_reason"] == "token_budget_exceeded"
    assert calls["search"] == 0


def test_deepsearch_stops_when_time_budget_exceeded(monkeypatch):
    _patch_deepsearch_basics(monkeypatch)
    calls = {"search": 0}

    def slow_generate_queries(*args, **kwargs):
        time.sleep(0.02)
        return ["q1"]

    monkeypatch.setattr(deepsearch_optimized, "_generate_queries", slow_generate_queries)

    def fake_search(*args, **kwargs):
        calls["search"] += 1
        return []

    monkeypatch.setattr(deepsearch_optimized, "_search_query", fake_search)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_max_tokens", 10_000, raising=False)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_max_seconds", 0.001, raising=False)

    result = deepsearch_optimized.run_deepsearch_optimized({"input": "AI"}, config={})

    assert result["budget_stop_reason"] == "time_budget_exceeded"
    assert calls["search"] == 0
