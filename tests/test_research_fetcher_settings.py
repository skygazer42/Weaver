from common.config import Settings


def test_settings_exposes_reader_and_fetcher_fields():
    s = Settings()
    assert hasattr(s, "reader_fallback_mode")
    assert hasattr(s, "reader_public_base")
    assert hasattr(s, "reader_self_hosted_base")
    assert hasattr(s, "research_fetch_timeout_s")
    assert hasattr(s, "research_fetch_max_bytes")
