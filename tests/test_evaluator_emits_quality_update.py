from types import SimpleNamespace

from agent.workflows import nodes
from agent.workflows.quality_assessor import QualityReport


class _FakeEvalLLM:
    def with_structured_output(self, _schema):
        return self

    def invoke(self, _messages, config=None):
        return SimpleNamespace(
            verdict="pass",
            dimensions=SimpleNamespace(
                coverage=0.9,
                accuracy=0.9,
                freshness=0.9,
                coherence=0.9,
            ),
            feedback="good",
            missing_topics=[],
            suggested_queries=[],
        )


def test_evaluator_emits_quality_update_event(monkeypatch):
    class FakeAssessor:
        def __init__(self, llm, config=None):
            pass

        def assess(self, report, scraped_content, sources=None):
            return QualityReport(
                claim_support_score=0.9,
                source_diversity_score=0.9,
                contradiction_free_score=1.0,
                citation_accuracy_score=0.9,
                citation_coverage_score=0.92,
                overall_score=0.9,
                recommendations=[],
            )

    emitted = []

    class DummyEmitter:
        def emit_sync(self, event_type, data):
            event_name = event_type.value if hasattr(event_type, "value") else str(event_type)
            emitted.append((event_name, data))

    monkeypatch.setattr(nodes, "_chat_model", lambda *args, **kwargs: _FakeEvalLLM())
    monkeypatch.setattr("agent.workflows.quality_assessor.QualityAssessor", FakeAssessor)

    emitter = DummyEmitter()
    monkeypatch.setattr(nodes, "get_emitter_sync", lambda thread_id: emitter)

    state = {
        "input": "Summarize AI chip market trends",
        "draft_report": "According to the report, revenue increased by 20% in 2024.",
        "scraped_content": [],
        "sources": [],
    }

    nodes.evaluator_node(state, config={"configurable": {"thread_id": "thread-eval"}})

    quality_events = [payload for name, payload in emitted if name == "quality_update"]
    assert quality_events, "expected evaluator to emit at least one quality_update event"
    assert quality_events[-1].get("stage") == "evaluation"
