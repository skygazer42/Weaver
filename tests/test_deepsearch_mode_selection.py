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
