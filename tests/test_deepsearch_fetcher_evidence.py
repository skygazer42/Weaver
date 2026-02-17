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
            self.markdown = "para1\n\npara2"
            self.title = "Example Title"
            self.retrieved_at = "2026-02-17T00:00:00+00:00"
            self.http_status = 200
            self.error = None
            self.attempts = 1

        def to_dict(self):
            return {
                "url": self.url,
                "raw_url": self.raw_url,
                "method": self.method,
                "title": self.title,
                "retrieved_at": self.retrieved_at,
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
    assert "\n\n" in passages[0]["text"]
    assert passages[0]["start_char"] == 0
    assert passages[0].get("page_title") == "Example Title"
    assert passages[0].get("retrieved_at") == "2026-02-17T00:00:00+00:00"
    assert passages[0].get("method") == "direct_http"


def test_build_fetcher_evidence_filters_cookie_banner_passages(monkeypatch):
    monkeypatch.setattr(
        deepsearch_optimized.settings,
        "deepsearch_enable_research_fetcher",
        True,
        raising=False,
    )

    cookie = (
        "We use cookies to improve your experience. Accept all cookies. Cookie preferences. Privacy Policy."
    )
    body = (
        "This is the actual article body. It contains multiple sentences. "
        "It should be preferred over boilerplate content."
    )
    markdown = f"{cookie}\n\n# Article\n\n{(body + ' ') * 30}".strip()

    class FakePage:
        def __init__(self, url: str):
            self.url = url
            self.raw_url = url
            self.method = "direct_http"
            self.title = "Example Title"
            self.retrieved_at = "2026-02-17T00:00:00+00:00"
            self.text = ""
            self.markdown = markdown
            self.http_status = 200
            self.error = None
            self.attempts = 1

        def to_dict(self):
            return {
                "url": self.url,
                "raw_url": self.raw_url,
                "method": self.method,
                "title": self.title,
                "retrieved_at": self.retrieved_at,
                "text": self.text,
                "markdown": self.markdown,
                "http_status": self.http_status,
                "error": self.error,
                "attempts": self.attempts,
            }

    class FakeFetcher:
        def fetch_many(self, urls):
            return [FakePage(urls[0])]

    monkeypatch.setattr(deepsearch_optimized, "ContentFetcher", lambda: FakeFetcher())

    _fetched_pages, passages = deepsearch_optimized._build_fetcher_evidence(["https://example.com/"])
    assert passages

    combined = "\n\n".join([p.get("text", "") for p in passages]).lower()
    assert "accept all cookies" not in combined
    assert "actual article body" in combined
