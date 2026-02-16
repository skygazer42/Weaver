import threading
import types

from tools.research.content_fetcher import ContentFetcher


def test_fetch_many_respects_per_domain_concurrency(monkeypatch):
    import tools.research.content_fetcher as mod

    monkeypatch.setattr(mod.settings, "research_fetch_cache_ttl_s", 0.0, raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_render_mode", "off", raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_concurrency", 2, raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_concurrency_per_domain", 1, raising=False)

    call_lock = threading.Lock()
    call_index = {"n": 0}
    first_active = threading.Event()
    allow_first_finish = threading.Event()
    second_started = threading.Event()

    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/plain"}
        content = b"ok"
        text = "ok"

        def iter_content(self, chunk_size=65536):
            yield self.content

        def close(self):
            return None

    def fake_get(url, timeout=None, headers=None, **kwargs):
        with call_lock:
            idx = call_index["n"]
            call_index["n"] += 1
        if idx == 0:
            first_active.set()
            assert allow_first_finish.wait(0.8), "first request never released"
        else:
            second_started.set()
        return FakeResp()

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))

    result: dict = {}

    def run():
        f = ContentFetcher()
        result["pages"] = f.fetch_many(["https://example.com/1", "https://example.com/2"])

    t = threading.Thread(target=run, daemon=True)
    t.start()

    assert first_active.wait(0.8), "first request never started"
    assert second_started.wait(0.1) is False, "second request should be blocked by per-domain limit"

    allow_first_finish.set()
    t.join(timeout=2.0)
    assert t.is_alive() is False, "fetch_many thread did not complete"

    pages = result.get("pages") or []
    assert len(pages) == 2


def test_fetch_many_allows_parallelism_across_domains(monkeypatch):
    import tools.research.content_fetcher as mod

    monkeypatch.setattr(mod.settings, "research_fetch_cache_ttl_s", 0.0, raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_render_mode", "off", raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_concurrency", 2, raising=False)
    monkeypatch.setattr(mod.settings, "research_fetch_concurrency_per_domain", 1, raising=False)

    call_lock = threading.Lock()
    call_index = {"n": 0}
    first_active = threading.Event()
    allow_first_finish = threading.Event()
    second_started = threading.Event()

    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/plain"}
        content = b"ok"
        text = "ok"

        def iter_content(self, chunk_size=65536):
            yield self.content

        def close(self):
            return None

    def fake_get(url, timeout=None, headers=None, **kwargs):
        with call_lock:
            idx = call_index["n"]
            call_index["n"] += 1
        if idx == 0:
            first_active.set()
            assert allow_first_finish.wait(0.8), "first request never released"
        else:
            second_started.set()
        return FakeResp()

    monkeypatch.setattr(mod, "requests", types.SimpleNamespace(get=fake_get))

    result: dict = {}

    def run():
        f = ContentFetcher()
        result["pages"] = f.fetch_many(["https://a.example.com/1", "https://b.example.com/2"])

    t = threading.Thread(target=run, daemon=True)
    t.start()

    assert first_active.wait(0.8), "first request never started"
    assert second_started.wait(0.8) is True, "second domain should start while first is blocked"

    allow_first_finish.set()
    t.join(timeout=2.0)
    assert t.is_alive() is False

    pages = result.get("pages") or []
    assert len(pages) == 2
