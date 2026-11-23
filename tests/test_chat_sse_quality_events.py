import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

import main
from agent.core.events import EventEmitter, ToolEvent


@pytest.mark.asyncio
async def test_chat_sse_no_key_does_not_emit_quality_update(monkeypatch):
    monkeypatch.setattr(main.settings, "openai_api_key", "")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/chat/sse",
            json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
        )

    assert resp.status_code == 200
    text = resp.text
    assert "event: error" in text
    assert "event: quality_update" not in text


@pytest.mark.asyncio
async def test_stream_flushes_queued_quality_update_before_graph_completion(monkeypatch):
    emitter = EventEmitter(thread_id="thread_test")
    quality_event_released = asyncio.Event()

    class _DummyGraph:
        async def astream_events(self, *args, **kwargs):
            await emitter.emit(
                ToolEvent.QUALITY_UPDATE,
                {"stage": "epoch", "epoch": 1, "query_coverage_score": 0.4},
            )
            quality_event_released.set()
            await asyncio.sleep(0.2)
            yield {
                "event": "on_graph_end",
                "name": "agent",
                "data": {"output": {"is_complete": True, "final_report": "done"}},
            }

    async def _noop_async(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "research_graph", _DummyGraph())
    monkeypatch.setattr(main, "get_emitter", _noop_async)
    monkeypatch.setattr(main, "remove_emitter", _noop_async)
    monkeypatch.setattr(main, "store_interaction", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "fetch_memories", lambda *args, **kwargs: [])
    monkeypatch.setattr(main.browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.sandbox_browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_browser_stream_conn_active", lambda *args, **kwargs: True)
    monkeypatch.setattr(main.settings, "enable_file_logging", False, raising=False)

    async def _fake_get_emitter(thread_id):
        return emitter

    monkeypatch.setattr(main, "get_emitter", _fake_get_emitter)

    stream = main.stream_agent_events("hi", thread_id="thread_test")

    first_chunk = await anext(stream)
    first_payload = json.loads(first_chunk[2:])
    assert first_payload["type"] == "status"

    second_chunk_task = asyncio.create_task(anext(stream))
    await asyncio.wait_for(quality_event_released.wait(), timeout=0.05)
    second_chunk = await asyncio.wait_for(second_chunk_task, timeout=0.05)
    payload = json.loads(second_chunk[2:])

    assert payload["type"] == "quality_update"
    assert payload["data"]["stage"] == "epoch"

    remaining = []
    async for chunk in stream:
        remaining.append(chunk)

    remaining_payloads = [json.loads(chunk[2:]) for chunk in remaining if chunk.startswith("0:")]
    remaining_types = [payload["type"] for payload in remaining_payloads]
    assert "completion" in remaining_types
