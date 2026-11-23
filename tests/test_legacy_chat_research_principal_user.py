import pytest
from httpx import ASGITransport, AsyncClient

import main
from common.thread_ownership import get_thread_owner


@pytest.mark.asyncio
async def test_chat_stream_uses_principal_user_when_internal_auth_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")
    monkeypatch.setattr(main.settings, "openai_api_key", "dummy")

    seen = {}

    async def _fake_stream_agent_events(
        input_text: str,
        *,
        thread_id: str,
        model: str,
        search_mode,
        agent_id=None,
        images=None,
        user_id: str,
        **_,
    ):
        seen["user_id"] = user_id
        yield '0:{"type":"done","data":{}}\n'

    monkeypatch.setattr(main, "stream_agent_events", _fake_stream_agent_events)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/chat",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "alice",
            },
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "user_id": "spoofed",
                "stream": True,
            },
        )

    assert resp.status_code == 200
    assert seen.get("user_id") == "alice"
    thread_id = resp.headers.get("x-thread-id")
    assert thread_id
    assert get_thread_owner(thread_id) == "alice"


@pytest.mark.asyncio
async def test_research_stream_uses_principal_user_when_internal_auth_enabled(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "test-key")
    monkeypatch.setitem(main.settings.__dict__, "auth_user_header", "X-Weaver-User")

    seen = {}

    async def _fake_stream_agent_events(
        input_text: str,
        *,
        thread_id: str,
        model: str | None = None,
        search_mode=None,
        agent_id=None,
        images=None,
        user_id: str | None = None,
    ):
        seen["user_id"] = user_id
        yield '0:{"type":"done","data":{}}\n'

    monkeypatch.setattr(main, "stream_agent_events", _fake_stream_agent_events)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/research",
            headers={
                "Authorization": "Bearer test-key",
                "X-Weaver-User": "alice",
            },
            params={"query": "hi"},
        )

    assert resp.status_code == 200
    assert seen.get("user_id") == "alice"
    thread_id = resp.headers.get("x-thread-id")
    assert thread_id
    assert get_thread_owner(thread_id) == "alice"

