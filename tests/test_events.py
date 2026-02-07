import asyncio

import pytest

from agent.core.events import EventEmitter, ToolEventType


@pytest.mark.asyncio
async def test_emit_sync_reaches_async_listeners_on_bound_loop():
    emitter = EventEmitter(thread_id="t_events")
    emitter._bind_loop(asyncio.get_running_loop())

    queue: asyncio.Queue = asyncio.Queue()

    async def listener(event):
        await queue.put(event)

    emitter.on_event(listener)

    emitter.emit_sync(ToolEventType.TOOL_START, {"tool": "unit_test", "args": {"x": 1}})
    event = await asyncio.wait_for(queue.get(), timeout=1.0)

    assert event.type == ToolEventType.TOOL_START
    assert event.seq >= 1


def test_sse_includes_id_line_for_resume():
    emitter = EventEmitter(thread_id="t_sse")
    # Run in a local loop (no listeners) to generate an event.
    asyncio.run(emitter.emit(ToolEventType.TOOL_PROGRESS, {"tool": "unit_test", "message": "ok"}))

    events = emitter.get_buffered_events()
    assert events
    sse = events[-1].to_sse()
    assert sse.startswith(f"id: {events[-1].seq}\n")
    assert "event: tool_progress\n" in sse
