import json
import operator
from typing import Annotated, Any
from typing_extensions import TypedDict

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import Command


class PlanState(TypedDict, total=False):
    research_plan: list[str]


class DraftState(TypedDict, total=False):
    draft_report: str
    final_report: str


class SourcesState(TypedDict, total=False):
    scraped_content: Annotated[list[dict[str, Any]], operator.add]
    compressed_knowledge: dict
    human_guidance: str


def _graph_config(thread_id: str) -> dict:
    return {
        "configurable": {"thread_id": thread_id, "allow_interrupts": True, "human_review": False},
        "recursion_limit": 10,
    }


def test_hitl_plan_review_node_interrupts_and_applies_updated_plan(monkeypatch: pytest.MonkeyPatch):
    from common.config import settings

    monkeypatch.setattr(settings, "hitl_checkpoints", "plan", raising=False)

    from agent.workflows.nodes import hitl_plan_review_node

    cp = MemorySaver()
    builder = StateGraph(PlanState)
    builder.add_node("review", hitl_plan_review_node)
    builder.add_edge(START, "review")
    builder.add_edge("review", END)
    graph = builder.compile(checkpointer=cp)

    out1 = graph.invoke({"research_plan": ["q1", "q2"]}, _graph_config("plan-1"))
    assert "__interrupt__" in out1
    interrupt_value = out1["__interrupt__"][0].value
    assert isinstance(interrupt_value, dict)
    assert interrupt_value.get("checkpoint") == "plan"
    assert "instruction" in interrupt_value
    assert "content" in interrupt_value

    updated_plan = ["cats", "dogs"]
    out2 = graph.invoke(Command(resume={"content": json.dumps(updated_plan)}), _graph_config("plan-1"))
    assert out2.get("research_plan") == updated_plan


def test_hitl_draft_review_node_interrupts_and_applies_updated_content(monkeypatch: pytest.MonkeyPatch):
    from common.config import settings

    monkeypatch.setattr(settings, "hitl_checkpoints", "draft", raising=False)

    from agent.workflows.nodes import hitl_draft_review_node

    cp = MemorySaver()
    builder = StateGraph(DraftState)
    builder.add_node("review", hitl_draft_review_node)
    builder.add_edge(START, "review")
    builder.add_edge("review", END)
    graph = builder.compile(checkpointer=cp)

    out1 = graph.invoke({"draft_report": "draft v1", "final_report": "draft v1"}, _graph_config("draft-1"))
    assert "__interrupt__" in out1
    interrupt_value = out1["__interrupt__"][0].value
    assert isinstance(interrupt_value, dict)
    assert interrupt_value.get("checkpoint") == "draft"
    assert "instruction" in interrupt_value
    assert interrupt_value.get("content") == "draft v1"

    out2 = graph.invoke(Command(resume={"content": "draft v2"}), _graph_config("draft-1"))
    assert out2.get("draft_report") == "draft v2"
    assert out2.get("final_report") == "draft v2"


def test_human_review_node_interrupts_when_final_checkpoint_enabled(monkeypatch: pytest.MonkeyPatch):
    from common.config import settings

    monkeypatch.setattr(settings, "hitl_checkpoints", "final", raising=False)

    from agent.workflows.nodes import human_review_node

    cp = MemorySaver()
    builder = StateGraph(DraftState)
    builder.add_node("review", human_review_node)
    builder.add_edge(START, "review")
    builder.add_edge("review", END)
    graph = builder.compile(checkpointer=cp)

    out1 = graph.invoke({"final_report": "report v1"}, _graph_config("final-1"))
    assert "__interrupt__" in out1
    interrupt_value = out1["__interrupt__"][0].value
    assert isinstance(interrupt_value, dict)
    assert "instruction" in interrupt_value
    assert interrupt_value.get("content") == "report v1"


def test_hitl_sources_review_node_interrupts_and_saves_guidance(monkeypatch: pytest.MonkeyPatch):
    from common.config import settings

    monkeypatch.setattr(settings, "hitl_checkpoints", "sources", raising=False)

    from agent.workflows.nodes import hitl_sources_review_node

    cp = MemorySaver()
    builder = StateGraph(SourcesState)
    builder.add_node("review", hitl_sources_review_node)
    builder.add_edge(START, "review")
    builder.add_edge("review", END)
    graph = builder.compile(checkpointer=cp)

    out1 = graph.invoke(
        {
            "scraped_content": [
                {
                    "query": "q1",
                    "results": [{"url": "https://example.com", "title": "Example", "snippet": "Hello"}],
                }
            ],
            "compressed_knowledge": {
                "summary": "Summary",
                "facts": [
                    {
                        "fact": "Fact 1",
                        "source": "https://example.com",
                        "confidence": 0.9,
                        "category": "background",
                    }
                ],
                "statistics": [],
                "key_entities": ["Example"],
                "subtopics": {},
            },
        },
        _graph_config("sources-1"),
    )
    assert "__interrupt__" in out1
    interrupt_value = out1["__interrupt__"][0].value
    assert isinstance(interrupt_value, dict)
    assert interrupt_value.get("checkpoint") == "sources"
    assert "instruction" in interrupt_value

    out2 = graph.invoke(
        Command(resume={"content": "Please focus on evidence quality."}),
        _graph_config("sources-1"),
    )
    assert out2.get("human_guidance") == "Please focus on evidence quality."
