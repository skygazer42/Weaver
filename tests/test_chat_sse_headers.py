import asyncio
import uuid

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_chat_sse_sets_thread_header_even_on_error(monkeypatch):
    monkeypatch.setattr(main.settings, "openai_api_key", "")
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/chat/sse",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 200
        assert resp.headers.get("X-Thread-ID")


@pytest.mark.asyncio
async def test_deep_research_replays_the_same_run_after_disconnect(monkeypatch):
    monkeypatch.setattr(main.settings, "openai_api_key", "dummy")
    monkeypatch.setattr(main.settings, "internal_api_key", "test-key")
    monkeypatch.setattr(main.settings, "auth_user_header", "X-Weaver-User")
    release = asyncio.Event()
    runs = []

    async def research(query, *, thread_id, **_):
        runs.append((query, thread_id))
        yield '0:{"type":"status","data":{"text":"researching"}}\n'
        await release.wait()
        yield '0:{"type":"completion","data":{"content":"finished report"}}\n'
        yield '0:{"type":"done","data":{}}\n'

    monkeypatch.setattr(main, "stream_agent_events", research)
    request = Request({"type": "http", "state": {"principal_id": "alice"}})
    payload = main.ChatRequest(messages=[{"role": "user", "content": "compare sources"}], search_mode="ultra")
    research_id = uuid.uuid4().hex
    initial = await main.chat_sse(request, payload, research_id=research_id)
    thread_id = initial.headers["X-Thread-ID"]
    assert thread_id != f"thread_{research_id}"
    subscriber = initial.body_iterator
    try:
        assert "id: 1\n" in await asyncio.wait_for(anext(subscriber), 2)
        await subscriber.aclose()
        duplicate = await main.chat_sse(request, payload, research_id=research_id)
        assert duplicate.headers["X-Thread-ID"] == thread_id
        assert "researching" in await asyncio.wait_for(anext(duplicate.body_iterator), 2)
        await duplicate.body_iterator.aclose()
        assert runs == [("compare sources", thread_id)]
        assert not main.active_streams[thread_id].done()
    finally:
        release.set()

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        path = f"/api/chat/sse/{research_id}"
        headers = {"Authorization": "Bearer test-key", "X-Weaver-User": "alice"}
        forbidden = await client.get(path, headers={**headers, "X-Weaver-User": "bob"})
        assert forbidden.status_code in {403, 404}
        replay = await client.get(path, headers={**headers, "Last-Event-ID": "1"})
        assert replay.status_code == 200
        assert replay.headers["X-Thread-ID"] == thread_id
        assert "researching" not in replay.text
        assert "id: 2\n" in replay.text and "finished report" in replay.text
        assert "event: done" in replay.text
        full_replay = await client.get(path, headers=headers)
        assert "researching" in full_replay.text and "finished report" in full_replay.text
        assert runs == [("compare sources", thread_id)]


@pytest.mark.asyncio
async def test_explicit_stop_cancels_resumable_research(monkeypatch):
    monkeypatch.setattr(main.settings, "openai_api_key", "dummy")
    monkeypatch.setattr(main.settings, "internal_api_key", "")

    graph_started = asyncio.Event()
    graph_closed = asyncio.Event()

    class ResearchGraph:
        async def astream_events(self, *_, **__):
            try:
                graph_started.set()
                await asyncio.Future()
                yield {}
            finally:
                graph_closed.set()

    monkeypatch.setattr(main, "research_graph", ResearchGraph())
    monkeypatch.setattr(main, "_store_search", lambda *_, **__: [])
    monkeypatch.setattr(main, "fetch_memories", lambda **_: [])
    request = Request({"type": "http"})
    payload = main.ChatRequest(messages=[{"role": "user", "content": "compare sources"}], search_mode="ultra")
    research_id = uuid.uuid4().hex
    initial = await main.chat_sse(request, payload, research_id=research_id)
    thread_id = initial.headers["X-Thread-ID"]
    task = main.active_streams[thread_id]
    try:
        assert "Initializing research agent" in await asyncio.wait_for(anext(initial.body_iterator), 2)
        await asyncio.wait_for(graph_started.wait(), 2)
        await initial.body_iterator.aclose()
        async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
            path = f"/api/chat/sse/{research_id}"
            cancelled = await client.delete(path)
            assert cancelled.json()["status"] == "cancelled"
            replay = await asyncio.wait_for(client.get(path), 2)
        assert "event: cancelled" in replay.text
        assert graph_closed.is_set()
    finally:
        task.cancel()

