import types

from tools.research.content_fetcher import ContentFetcher


class _Headers:
    def __init__(self, mapping):
        self._mapping = {str(k).lower(): str(v) for k, v in (mapping or {}).items()}

    def get(self, key, default=None):
        return self._mapping.get(str(key).lower(), default)


def test_content_fetcher_direct_uses_requests_and_strips_html(monkeypatch):
    calls = {"get": 0}
    seen = {"url": None, "timeout": None, "headers": None, "kwargs": None}

    class FakeResp:
        status_code = 200
        headers = _Headers({"Content-Type": "text/html; charset=utf-8"})
        content = b"<html><body>Hello</body></html>"
        text = "<html><body>Hello</body></html>"

        def iter_content(self, chunk_size=65536):
            yield self.content

    def fake_get(url, timeout=None, headers=None, **kwargs):
        calls["get"] += 1
        seen["url"] = url
        seen["timeout"] = timeout
        seen["headers"] = headers
        seen["kwargs"] = kwargs
        return FakeResp()

    import tools.research.content_fetcher as mod

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))

    f = ContentFetcher()
    page = f.fetch("https://example.com/?utm_source=x")

    assert seen["url"] == "https://example.com/"  # canonicalized
    assert seen["timeout"] == mod.settings.research_fetch_timeout_s
    assert (seen["headers"] or {}).get("User-Agent") == mod.DEFAULT_UA

    assert page.method == "direct_http"
    assert page.http_status == 200
    assert page.text == "Hello"
    assert calls["get"] == 1


def test_content_fetcher_blocks_localhost_without_network(monkeypatch):
    import tools.research.content_fetcher as mod

    called = {"get": False}

    def fake_get(*args, **kwargs):
        called["get"] = True
        raise AssertionError("requests.get should not be called for blocked hosts")

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))

    f = ContentFetcher()
    page = f.fetch("http://localhost:8000/")
    assert called["get"] is False
    assert page.error
    assert "blocked" in page.error.lower()
