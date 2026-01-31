import pytest


def test_settings_allows_missing_openai_api_key(monkeypatch):
    """Settings should be constructible in dev/test even without OPENAI_API_KEY."""
    # Avoid relying on a local .env file in unit tests.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from common.config import Settings

    s = Settings(_env_file=None)
    assert s.openai_api_key == ""
