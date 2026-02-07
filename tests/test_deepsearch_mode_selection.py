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
