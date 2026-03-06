import sys
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, SystemMessage

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.workflows import nodes


def test_agent_node_delegates_simple_verification_query_to_fast_search(monkeypatch):
    called = {"fast": False}

    def fake_fast(state, config):
        called["fast"] = True
        return {
            "draft_report": "Paris",
            "final_report": "Paris",
            "messages": [AIMessage(content="Paris")],
            "is_complete": False,
        }

    def fail_build_tools(_config):
        raise AssertionError("full tool agent should be skipped for simple verification query")

    monkeypatch.setattr(nodes, "_answer_simple_agent_query", fake_fast, raising=False)
    monkeypatch.setattr(nodes, "build_agent_tools", fail_build_tools)

    result = nodes.agent_node(
        {
            "input": "Use current web search to verify: What is the capital of France? Reply with exactly Paris.",
        },
        {"configurable": {}},
    )

    assert called["fast"] is True
    assert result["final_report"] == "Paris"


def test_agent_node_keeps_full_tool_agent_for_complex_research_queries(monkeypatch):
    class FakeAgent:
        def invoke(self, payload, config=None):
            assert payload["messages"]
            return {"messages": [AIMessage(content="Structured comparison")]}

    def fail_fast(_state, _config):
        raise AssertionError("fast search path should be skipped for complex research queries")

    monkeypatch.setattr(nodes, "_answer_simple_agent_query", fail_fast, raising=False)
    monkeypatch.setattr(nodes, "build_agent_tools", lambda _config: [])
    monkeypatch.setattr(nodes, "build_tool_agent", lambda **_kwargs: FakeAgent())
    monkeypatch.setattr(nodes, "detect_stuck", lambda _messages, threshold=1: False)

    result = nodes.agent_node(
        {
            "input": "Compare EV battery supply chain risks across the US and EU in 2025, including policy and sourcing trade-offs.",
        },
        {"configurable": {}},
    )

    assert result["final_report"] == "Structured comparison"


def test_fast_agent_path_preserves_seeded_system_messages(monkeypatch):
    captured = {}

    class FakeLLM:
        def invoke(self, messages, config=None):
            captured["messages"] = messages
            return SimpleNamespace(content="Paris")

    monkeypatch.setattr(
        nodes,
        "_run_fast_agent_search",
        lambda _query, _config: (
            "tavily_search",
            [{"title": "France", "url": "https://example.com/fr", "snippet": "Paris is the capital of France."}],
        ),
        raising=False,
    )
    monkeypatch.setattr(nodes, "_chat_model", lambda _model, temperature=0.2: FakeLLM())
    monkeypatch.setattr(nodes, "_model_for_task", lambda *_args, **_kwargs: "deepseek-chat")

    result = nodes._answer_simple_agent_query(
        {
            "input": "Use current web search to verify: What is the capital of France? Reply with exactly Paris.",
            "messages": [
                SystemMessage(content="Custom agent instruction"),
                SystemMessage(content="Relevant past knowledge:\n- France is a country in Europe"),
            ],
        },
        {"configurable": {}},
    )

    assert result["final_report"] == "Paris"
    system_contents = [msg.content for msg in captured["messages"] if isinstance(msg, SystemMessage)]
    assert "Custom agent instruction" in system_contents
    assert "Relevant past knowledge:\n- France is a country in Europe" in system_contents
