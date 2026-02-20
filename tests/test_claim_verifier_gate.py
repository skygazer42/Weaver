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


def _state_with_contradiction():
    return {
        "input": "Summarize AI chip market trends",
        "draft_report": "According to the annual report, the company's revenue increased in 2024.",
        "scraped_content": [
            {
                "query": "revenue trend",
                "results": [
                    {
                        "url": "https://example.com/earnings?utm_source=test",
                        "summary": "The company's revenue did not increase in 2024 and decreased by 5%.",
                    }
                ],
            }
        ],
        "sources": [],
    }


def test_claim_verifier_gate_forces_revise_when_contradictions_found(monkeypatch):
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
    monkeypatch.setattr(nodes.settings, "claim_verifier_gate_max_contradicted", 0, raising=False)
    monkeypatch.setattr(nodes.settings, "claim_verifier_gate_max_unsupported", 0, raising=False)

    result = nodes.evaluator_node(_state_with_contradiction(), config={})

    assert result["verdict"] == "revise"
    assert "Claim verifier" in result["evaluation"]


def test_claim_verifier_gate_allows_pass_when_threshold_permits(monkeypatch):
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
    monkeypatch.setattr(nodes.settings, "claim_verifier_gate_max_contradicted", 2, raising=False)
    monkeypatch.setattr(nodes.settings, "claim_verifier_gate_max_unsupported", 2, raising=False)

    result = nodes.evaluator_node(_state_with_contradiction(), config={})

    assert result["verdict"] == "pass"
