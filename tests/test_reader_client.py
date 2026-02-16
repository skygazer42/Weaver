import pytest

from tools.research.reader_client import ReaderClient


def test_reader_client_builds_public_url_exact_match():
    c = ReaderClient(mode="public", public_base="https://r.jina.ai", self_hosted_base="")
    out = c.build_reader_url("https://example.com/a?utm_source=x")
    assert out == "https://r.jina.ai/https://example.com/a?utm_source=x"


def test_reader_client_prefers_self_hosted_when_configured():
    c = ReaderClient(
        mode="self_hosted",
        public_base="https://r.jina.ai",
        self_hosted_base="http://reader.local",
    )
    out = c.build_reader_url("https://example.com/")
    assert out == "http://reader.local/https://example.com/"


def test_reader_client_supports_both_mode_preferring_self_hosted():
    c = ReaderClient(
        mode="both",
        public_base="https://r.jina.ai",
        self_hosted_base="http://reader.local/",
    )
    out = c.build_reader_url("https://example.com/")
    assert out == "http://reader.local/https://example.com/"


def test_reader_client_supports_both_mode_falling_back_to_public():
    c = ReaderClient(mode="both", public_base="https://r.jina.ai/", self_hosted_base="")
    out = c.build_reader_url("https://example.com/")
    assert out == "https://r.jina.ai/https://example.com/"


def test_reader_client_rejects_unknown_mode():
    c = ReaderClient(mode="wat", public_base="https://r.jina.ai", self_hosted_base="")
    with pytest.raises(ValueError):
        c.build_reader_url("https://example.com/")


def test_reader_client_requires_self_hosted_base_when_forced():
    c = ReaderClient(mode="self_hosted", public_base="https://r.jina.ai", self_hosted_base="")
    with pytest.raises(ValueError):
        c.build_reader_url("https://example.com/")
