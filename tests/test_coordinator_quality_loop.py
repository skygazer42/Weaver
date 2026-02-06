from agent.workflows import nodes
from agent.workflows.agents.coordinator import CoordinatorAction, ResearchCoordinator


class _NeverInvokeLLM:
    def invoke(self, _messages, config=None):
        raise AssertionError("LLM should not be called when quality guardrails decide action")


def test_coordinator_prefers_research_for_low_quality_signals():
    coordinator = ResearchCoordinator(_NeverInvokeLLM())

    decision = coordinator.decide_next_action(
        topic="AI chips",
        num_queries=4,
        num_sources=8,
        num_summaries=2,
        current_epoch=1,
        max_epochs=4,
        quality_score=0.42,
        quality_gap_count=3,
        citation_accuracy=0.3,
    )

    assert decision.action == CoordinatorAction.RESEARCH


def test_coordinator_allows_complete_for_high_quality_signals():
    coordinator = ResearchCoordinator(_NeverInvokeLLM())

    decision = coordinator.decide_next_action(
        topic="AI chips",
        num_queries=4,
        num_sources=12,
        num_summaries=3,
        current_epoch=1,
        max_epochs=4,
        quality_score=0.91,
        quality_gap_count=0,
        citation_accuracy=0.86,
    )

    assert decision.action == CoordinatorAction.COMPLETE


def test_coordinator_node_routes_low_quality_to_research_without_llm(monkeypatch):
    monkeypatch.setattr(nodes, "_chat_model", lambda *args, **kwargs: _NeverInvokeLLM())

    state = {
        "input": "Summarize AI chip market",
        "research_plan": ["q1"],
        "scraped_content": [{"query": "q1", "results": []}],
        "summary_notes": ["draft summary"],
        "revision_count": 0,
        "max_revisions": 2,
        "quality_overall_score": 0.4,
        "quality_gap_count": 2,
        "eval_dimensions": {"citation_coverage": 0.35, "coverage": 0.7},
        "missing_topics": ["pricing"],
    }

    result = nodes.coordinator_node(state, config={})

    assert result["coordinator_action"] == "research"
