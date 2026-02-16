from tools.research.reader_client import ReaderClient


def test_reader_client_builds_public_url():
    c = ReaderClient(mode="public", public_base="https://r.jina.ai", self_hosted_base="")
    out = c.build_reader_url("https://example.com/a?utm_source=x")
    assert out.startswith("https://r.jina.ai/")


def test_reader_client_prefers_self_hosted_when_configured():
    c = ReaderClient(
        mode="self_hosted",
        public_base="https://r.jina.ai",
        self_hosted_base="http://reader.local",
    )
    out = c.build_reader_url("https://example.com/")
    assert out.startswith("http://reader.local")
