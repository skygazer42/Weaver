import json

import pytest

import main


class _Msg:
    def __init__(self, content: str):
        self.content = content


class _DummyGraph:
    async def astream_events(self, *args, **kwargs):
        # Planner starts and streams tokens (should NOT reach main answer stream)
        yield {"event": "on_node_start", "name": "planner", "data": {}}
        yield {
            "event": "on_chat_model_stream",
            "name": "planner",
            "data": {"chunk": {"content": "PLAN_TOKEN"}},
        }
        yield {
            "event": "on_node_end",
            "name": "planner",
            "data": {"output": {"messages": [_Msg("planner message")], "is_complete": False}},
        }

        # Writer streams tokens (allowed) but its "messages" should not be forwarded as type=message
        yield {"event": "on_node_start", "name": "writer", "data": {}}
        yield {
            "event": "on_chat_model_stream",
            "name": "writer",
            "data": {"chunk": {"content": "WRITER_TOKEN"}},
        }
        yield {
            "event": "on_node_end",
            "name": "writer",
            "data": {"output": {"messages": [_Msg("writer message")], "is_complete": False}},
        }

        # Final completion
        yield {
            "event": "on_graph_end",
            "name": "human_review",
            "data": {"output": {"is_complete": True, "final_report": "FINAL"}},
        }


async def _noop_async(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_stream_does_not_forward_intermediate_messages_or_planner_tokens(monkeypatch):
    monkeypatch.setattr(main, "research_graph", _DummyGraph())
    monkeypatch.setattr(main, "add_memory_entry", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "store_interaction", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "fetch_memories", lambda *args, **kwargs: [])
    monkeypatch.setattr(main, "remove_emitter", _noop_async)
    monkeypatch.setattr(main.browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.sandbox_browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_browser_stream_conn_active", lambda *args, **kwargs: True)
    monkeypatch.setattr(main.settings, "enable_file_logging", False, raising=False)

    chunks: list[str] = []
    async for chunk in main.stream_agent_events("hi", thread_id="thread_test"):
        chunks.append(chunk)

    payloads = []
    for chunk in chunks:
        if not chunk.startswith("0:"):
            continue
        payloads.append(json.loads(chunk[2:]))

    types = [p.get("type") for p in payloads]

    # Main answer stream should not receive node output "messages" at all.
    assert "message" not in types
    # Planner summary should be surfaced as a separate thinking event (accordion), not main answer.
    assert "thinking" in types

    # Planner tokens must not leak into main text stream.
    text_chunks = [p for p in payloads if p.get("type") == "text"]
    text = "".join((c.get("data", {}) or {}).get("content", "") for c in text_chunks)
    assert "PLAN_TOKEN" not in text

    # Final answer still arrives.
    assert "completion" in types
    completion_payload = payloads[types.index("completion")]
    assert completion_payload.get("data", {}).get("content") == "FINAL"
