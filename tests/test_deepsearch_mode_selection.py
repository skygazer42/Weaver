from agent.workflows import deepsearch_optimized, nodes


def test_deepsearch_node_uses_auto_runner(monkeypatch):
    called = {"auto": False}

    def fake_auto(state, config):
        called["auto"] = True
        return {"runner": "auto", "state": state}

    def fake_legacy(state, config):
        raise AssertionError("legacy run_deepsearch should not be called")

    monkeypatch.setattr(nodes, "run_deepsearch_auto", fake_auto, raising=False)
    monkeypatch.setattr(nodes, "run_deepsearch", fake_legacy, raising=False)

    result = nodes.deepsearch_node({"input": "test"}, {})

    assert called["auto"] is True
    assert result["runner"] == "auto"


def test_run_deepsearch_auto_respects_runtime_override(monkeypatch):
    called = {"tree": False, "linear": False}

    def fake_tree(state, config):
        called["tree"] = True
        return {"mode": "tree"}

    def fake_linear(state, config):
        called["linear"] = True
        return {"mode": "linear"}

    monkeypatch.setattr(deepsearch_optimized, "run_deepsearch_tree", fake_tree)
    monkeypatch.setattr(deepsearch_optimized, "run_deepsearch_optimized", fake_linear)
    monkeypatch.setattr(deepsearch_optimized.settings, "tree_exploration_enabled", True)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_mode", "tree", raising=False)

    result = deepsearch_optimized.run_deepsearch_auto(
        {"input": "test"},
        {"configurable": {"deepsearch_mode": "linear"}},
    )

    assert called["linear"] is True
    assert called["tree"] is False
    assert result["mode"] == "linear"


def test_deepsearch_node_emits_visualization_events(monkeypatch):
    emitted = []

    class DummyEmitter:
        def emit_sync(self, event_type, data):
            event_name = event_type.value if hasattr(event_type, "value") else str(event_type)
            emitted.append((event_name, data))

    def fake_auto(state, config):
        return {
            "final_report": "final report",
            "quality_summary": {"query_coverage_score": 0.8, "freshness_warning": ""},
            "deepsearch_artifacts": {"research_tree": {"id": "root", "children": []}},
        }

    monkeypatch.setattr(nodes, "run_deepsearch_auto", fake_auto, raising=False)
    monkeypatch.setattr(nodes, "get_emitter_sync", lambda _thread_id: DummyEmitter(), raising=False)

    result = nodes.deepsearch_node(
        {"input": "test topic", "cancel_token_id": "thread_test"},
        {"configurable": {"thread_id": "thread_test"}},
    )

    event_types = [name for name, _ in emitted]

    assert result["final_report"] == "final report"
    assert event_types[0] == "research_node_start"
    assert "quality_update" in event_types
    assert "research_tree_update" in event_types
    assert event_types[-1] == "research_node_complete"
    quality_events = [data for name, data in emitted if name == "quality_update"]
    assert quality_events
    assert quality_events[0].get("stage") == "final"


def test_deepsearch_node_emits_compact_unique_preview_sources(monkeypatch):
    emitted = []

    class DummyEmitter:
        def emit_sync(self, event_type, data):
            event_name = event_type.value if hasattr(event_type, "value") else str(event_type)
            emitted.append((event_name, data))

    def fake_auto(state, config):
        return {
            "final_report": "final report",
            "quality_summary": {"query_coverage_score": 0.8},
            "scraped_content": [
                {
                    "query": "q1",
                    "results": [
                        {
                            "title": "A",
                            "url": "https://example.com/a",
                            "provider": "serper",
                            "published_date": "2026-02-01",
                        },
                        {
                            "title": "B",
                            "url": "https://example.com/b",
                            "provider": "serper",
                            "published_date": "2026-01-20",
                        },
                        {
                            "title": "B duplicate",
                            "url": "https://example.com/b",
                            "provider": "serper",
                            "published_date": "2026-01-20",
                        },
                    ],
                },
                {
                    "query": "q2",
                    "results": [
                        {"title": "C", "url": "https://example.com/c"},
                        {"title": "D", "url": "https://example.com/d"},
                        {"title": "E", "url": "https://example.com/e"},
                        {"title": "F", "url": "https://example.com/f"},
                    ],
                },
            ],
        }

    monkeypatch.setattr(nodes, "run_deepsearch_auto", fake_auto, raising=False)
    monkeypatch.setattr(nodes, "get_emitter_sync", lambda _thread_id: DummyEmitter(), raising=False)

    nodes.deepsearch_node(
        {"input": "test topic", "cancel_token_id": "thread_test"},
        {"configurable": {"thread_id": "thread_test"}},
    )

    complete_events = [data for name, data in emitted if name == "research_node_complete"]
    assert complete_events

    sources = complete_events[0].get("sources", [])
    urls = [src.get("url") for src in sources]
    assert len(sources) <= 5
    assert len(urls) == len(set(urls))
    assert "https://example.com/a" in urls


def test_deepsearch_node_builds_preview_from_sources_fallback(monkeypatch):
    emitted = []

    class DummyEmitter:
        def emit_sync(self, event_type, data):
            event_name = event_type.value if hasattr(event_type, "value") else str(event_type)
            emitted.append((event_name, data))

    def fake_auto(state, config):
        return {
            "final_report": "final report",
            "quality_summary": {"query_coverage_score": 0.8},
            "sources": [
                {"title": "A", "url": "https://example.com/a", "provider": "serper"},
                {"title": "B", "url": "https://example.com/b", "provider": "serper"},
            ],
        }

    monkeypatch.setattr(nodes, "run_deepsearch_auto", fake_auto, raising=False)
    monkeypatch.setattr(nodes, "get_emitter_sync", lambda _thread_id: DummyEmitter(), raising=False)

    nodes.deepsearch_node(
        {"input": "test topic", "cancel_token_id": "thread_test"},
        {"configurable": {"thread_id": "thread_test"}},
    )

    complete_events = [data for name, data in emitted if name == "research_node_complete"]
    assert complete_events
    urls = [src.get("url") for src in complete_events[0].get("sources", [])]
    assert urls == ["https://example.com/a", "https://example.com/b"]


def test_deepsearch_node_skips_wrapper_events_when_runner_marks_emitted(monkeypatch):
    emitted = []

    class DummyEmitter:
        def emit_sync(self, event_type, data):
            event_name = event_type.value if hasattr(event_type, "value") else str(event_type)
            emitted.append((event_name, data))

    def fake_auto(state, config):
        return {
            "final_report": "final report",
            "quality_summary": {"query_coverage_score": 0.9},
            "_deepsearch_events_emitted": True,
        }

    monkeypatch.setattr(nodes, "run_deepsearch_auto", fake_auto, raising=False)
    monkeypatch.setattr(nodes, "get_emitter_sync", lambda _thread_id: DummyEmitter(), raising=False)

    nodes.deepsearch_node(
        {"input": "test topic", "cancel_token_id": "thread_test"},
        {"configurable": {"thread_id": "thread_test"}},
    )

    event_types = [name for name, _ in emitted]
    assert event_types == ["research_node_start"]


def test_run_deepsearch_auto_sets_events_emitted_marker(monkeypatch):
    def fake_linear(state, config):
        return {"mode": "linear"}

    monkeypatch.setattr(deepsearch_optimized, "run_deepsearch_optimized", fake_linear)
    monkeypatch.setattr(deepsearch_optimized.settings, "tree_exploration_enabled", False)
    monkeypatch.setattr(deepsearch_optimized.settings, "deepsearch_mode", "auto", raising=False)

    result = deepsearch_optimized.run_deepsearch_auto({"input": "test"}, {"configurable": {}})
    assert result["_deepsearch_events_emitted"] is True


def test_deepsearch_node_dedupes_preview_urls_after_tracking_normalization(monkeypatch):
    emitted = []

    class DummyEmitter:
        def emit_sync(self, event_type, data):
            event_name = event_type.value if hasattr(event_type, "value") else str(event_type)
            emitted.append((event_name, data))

    def fake_auto(state, config):
        return {
            "final_report": "final report",
            "quality_summary": {"query_coverage_score": 0.8},
            "scraped_content": [
                {
                    "query": "q1",
                    "results": [
                        {"title": "A", "url": "https://example.com/a?utm_source=newsletter"},
                        {"title": "A2", "url": "https://example.com/a/"},
                    ],
                }
            ],
        }

    monkeypatch.setattr(nodes, "run_deepsearch_auto", fake_auto, raising=False)
    monkeypatch.setattr(nodes, "get_emitter_sync", lambda _thread_id: DummyEmitter(), raising=False)

    nodes.deepsearch_node(
        {"input": "test topic", "cancel_token_id": "thread_test"},
        {"configurable": {"thread_id": "thread_test"}},
    )

    complete_events = [data for name, data in emitted if name == "research_node_complete"]
    assert complete_events
    urls = [src.get("url") for src in complete_events[0].get("sources", [])]
    assert urls == ["https://example.com/a"]


def test_deepsearch_node_dedupes_preview_urls_with_case_insensitive_host(monkeypatch):
    emitted = []

    class DummyEmitter:
        def emit_sync(self, event_type, data):
            event_name = event_type.value if hasattr(event_type, "value") else str(event_type)
            emitted.append((event_name, data))

    def fake_auto(state, config):
        return {
            "final_report": "final report",
            "quality_summary": {"query_coverage_score": 0.8},
            "scraped_content": [
                {
                    "query": "q1",
                    "results": [
                        {"title": "A", "url": "https://EXAMPLE.com/b"},
                        {"title": "B", "url": "https://example.com/b"},
                    ],
                }
            ],
        }

    monkeypatch.setattr(nodes, "run_deepsearch_auto", fake_auto, raising=False)
    monkeypatch.setattr(nodes, "get_emitter_sync", lambda _thread_id: DummyEmitter(), raising=False)

    nodes.deepsearch_node(
        {"input": "test topic", "cancel_token_id": "thread_test"},
        {"configurable": {"thread_id": "thread_test"}},
    )

    complete_events = [data for name, data in emitted if name == "research_node_complete"]
    assert complete_events
    urls = [src.get("url") for src in complete_events[0].get("sources", [])]
    assert urls == ["https://example.com/b"]
