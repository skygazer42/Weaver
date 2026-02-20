import pytest


def test_settings_quality_gate_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CITATION_GATE_MIN_COVERAGE", raising=False)
    monkeypatch.delenv("CLAIM_VERIFIER_GATE_MAX_CONTRADICTED", raising=False)
    monkeypatch.delenv("CLAIM_VERIFIER_GATE_MAX_UNSUPPORTED", raising=False)

    from common.config import Settings

    s = Settings(_env_file=None)
    assert s.citation_gate_min_coverage == pytest.approx(0.6)
    assert s.claim_verifier_gate_max_contradicted == 0
    assert s.claim_verifier_gate_max_unsupported == 0


def test_settings_quality_gate_env_overrides(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CITATION_GATE_MIN_COVERAGE", "0.75")
    monkeypatch.setenv("CLAIM_VERIFIER_GATE_MAX_CONTRADICTED", "2")
    monkeypatch.setenv("CLAIM_VERIFIER_GATE_MAX_UNSUPPORTED", "1")

    from common.config import Settings

    s = Settings(_env_file=None)
    assert s.citation_gate_min_coverage == pytest.approx(0.75)
    assert s.claim_verifier_gate_max_contradicted == 2
    assert s.claim_verifier_gate_max_unsupported == 1
