import types

from tools.research.content_fetcher import ContentFetcher


def test_content_fetcher_uses_cache_for_canonical_url(monkeypatch):
    import tools.research.content_fetcher as mod
    import tools.research.page_cache as page_cache

    monkeypatch.setattr(mod.settings, "research_fetch_cache_ttl_s", 60.0, raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_cache_max_entries", 10, raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_cache_store_errors", False, raising=False)

    page_cache.clear_fetched_page_cache()

    calls = {"get": 0}

    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/plain"}
        text = "ok"
        content = b"ok"

        def iter_content(self, chunk_size=65536):
            yield self.content

        def close(self):
            return None

    def fake_get(url, timeout=None, headers=None, **kwargs):
        calls["get"] += 1
        return FakeResp()

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))

    f = ContentFetcher()
    page1 = f.fetch("https://example.com/?utm_source=a")
    page2 = f.fetch("https://example.com/?utm_source=b")

    assert page1.url == "https://example.com/"
    assert page2.url == "https://example.com/"
    assert page2.text == "ok"
    assert calls["get"] == 1
