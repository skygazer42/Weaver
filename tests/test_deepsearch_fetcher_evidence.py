from agent.workflows import deepsearch_optimized


def test_build_fetcher_evidence_uses_fetch_many_and_dedupes(monkeypatch):
    monkeypatch.setattr(
        deepsearch_optimized.settings,
        "deepsearch_enable_research_fetcher",
        True,
        raising=False,
    )

    calls = {"urls": None}

    class FakePage:
        def __init__(self, url: str, text: str):
            self.url = url
            self.raw_url = url
            self.method = "direct_http"
            self.text = text
            self.markdown = None
            self.http_status = 200
            self.error = None
            self.attempts = 1

        def to_dict(self):
            return {
                "url": self.url,
                "raw_url": self.raw_url,
                "method": self.method,
                "text": self.text,
                "markdown": self.markdown,
                "http_status": self.http_status,
                "error": self.error,
                "attempts": self.attempts,
            }

    class FakeFetcher:
        def fetch_many(self, urls):
            calls["urls"] = list(urls)
            return [FakePage(urls[0], "hello world")]

    monkeypatch.setattr(deepsearch_optimized, "ContentFetcher", lambda: FakeFetcher())

    fetched_pages, passages = deepsearch_optimized._build_fetcher_evidence(
        [
            "https://example.com/?utm_source=a",
            "https://example.com/?utm_source=b",
        ]
    )

    assert calls["urls"] == ["https://example.com"]
    assert len(fetched_pages) == 1
    assert fetched_pages[0]["url"] == "https://example.com"
    assert passages
    assert passages[0]["url"] == "https://example.com"
    assert passages[0]["start_char"] == 0
