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


def _state():
    return {
        "input": "Summarize AI chip market trends",
        "draft_report": "2024年市场增长10%。",
        "scraped_content": [],
        "sources": [],
    }


def test_citation_gate_forces_revise_when_coverage_is_low(monkeypatch):
    class FakeAssessor:
        def __init__(self, llm, config=None):
            pass

        def assess(self, report, scraped_content, sources=None):
            return QualityReport(
                claim_support_score=0.9,
                source_diversity_score=0.9,
                contradiction_free_score=1.0,
                citation_accuracy_score=0.9,
                citation_coverage_score=0.25,
                overall_score=0.9,
                recommendations=[],
            )

    monkeypatch.setattr(nodes, "_chat_model", lambda *args, **kwargs: _FakeEvalLLM())
    monkeypatch.setattr("agent.workflows.quality_assessor.QualityAssessor", FakeAssessor)

    result = nodes.evaluator_node(_state(), config={})

    assert result["verdict"] == "revise"
    assert result["eval_dimensions"]["citation_coverage"] == 0.25
    assert "Citation gate" in result["evaluation"]


def test_citation_gate_allows_pass_when_coverage_is_high(monkeypatch):
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

    monkeypatch.setattr(nodes, "_chat_model", lambda *args, **kwargs: _FakeEvalLLM())
    monkeypatch.setattr("agent.workflows.quality_assessor.QualityAssessor", FakeAssessor)

    result = nodes.evaluator_node(_state(), config={})

    assert result["verdict"] == "pass"
    assert result["eval_dimensions"]["citation_coverage"] == 0.92
