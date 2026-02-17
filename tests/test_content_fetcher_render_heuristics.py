import types

from tools.research.content_fetcher import ContentFetcher


def test_content_fetcher_auto_renders_when_page_says_enable_javascript(monkeypatch):
    import tools.research.content_fetcher as mod

    monkeypatch.setattr(mod.settings, "research_fetch_cache_ttl_s", 0.0, raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_render_mode", "auto", raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_render_min_chars", 200, raising=False)

    calls = {"direct": 0, "reader": 0}

    phrase = "Please enable JavaScript and cookies to continue."
    repeated = (" " + phrase) * 20
    html = f"<html><body><p>{phrase}</p><p>{repeated}</p></body></html>"

    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        content = html.encode("utf-8")
        text = html

        def iter_content(self, chunk_size=65536):
            yield self.content

        def close(self):
            return None

    def fake_get(url, timeout=None, headers=None, **kwargs):
        if "r.jina.ai" in url:
            calls["reader"] += 1
            raise AssertionError("reader should not be called when render succeeds")
        calls["direct"] += 1
        return FakeResp()

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))

    import tools.crawl.crawler as crawler

    def fake_crawl_urls(urls, timeout=10):
        assert urls == ["https://example.com/"]
        rendered = ("Rendered content " * 30).strip()
        assert len(rendered) >= 200
        return [{"url": urls[0], "content": rendered}]

    monkeypatch.setattr(crawler, "crawl_urls", fake_crawl_urls)

    page = ContentFetcher().fetch("https://example.com/")
    assert page.method == "render_crawler"
    assert page.text and page.text.startswith("Rendered content")
    assert calls["direct"] == 1
    assert calls["reader"] == 0


def test_content_fetcher_auto_renders_cloudflare_interstitial(monkeypatch):
    import tools.research.content_fetcher as mod

    monkeypatch.setattr(mod.settings, "research_fetch_cache_ttl_s", 0.0, raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_render_mode", "auto", raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_render_min_chars", 200, raising=False)

    calls = {"direct": 0, "reader": 0}

    phrase = "Checking your browser before accessing"
    repeated = (" " + phrase) * 40
    html = f"<html><head><title>Just a moment...</title></head><body><p>{phrase}</p><p>{repeated}</p></body></html>"

    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        content = html.encode("utf-8")
        text = html

        def iter_content(self, chunk_size=65536):
            yield self.content

        def close(self):
            return None

    def fake_get(url, timeout=None, headers=None, **kwargs):
        if "r.jina.ai" in url:
            calls["reader"] += 1
            raise AssertionError("reader should not be called when render succeeds")
        calls["direct"] += 1
        return FakeResp()

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))

    import tools.crawl.crawler as crawler

    def fake_crawl_urls(urls, timeout=10):
        assert urls == ["https://example.com/"]
        rendered = ("Rendered content " * 30).strip()
        assert len(rendered) >= 200
        return [{"url": urls[0], "content": rendered}]

    monkeypatch.setattr(crawler, "crawl_urls", fake_crawl_urls)

    page = ContentFetcher().fetch("https://example.com/")
    assert page.method == "render_crawler"
    assert page.text and page.text.startswith("Rendered content")
    assert calls["direct"] == 1
    assert calls["reader"] == 0
