from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from typing import Any


def format_sse_event(*, event: str, data: Any, event_id: int | None = None) -> str:
    """
    Format a single Server-Sent Events (SSE) frame.

    We intentionally emit a single `data:` line containing JSON to keep client
    parsing simple and predictable.
    """
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


def format_sse_comment(comment: str = "keepalive") -> str:
    """
    Format a single SSE comment frame.

    Comments are ignored by SSE clients but keep connections alive through some proxies.
    """
    text = str(comment or "").strip() or "keepalive"
    return f": {text}\n\n"


def format_sse_retry(retry_ms: int) -> str:
    """
    Format an SSE `retry:` control frame.

    This hints the client how long to wait (in milliseconds) before reconnecting.
    """
    try:
        value = int(retry_ms)
    except Exception:
        value = 0
    if value < 0:
        value = 0
    return f"retry: {value}\n\n"


async def iter_with_sse_keepalive(
    source: AsyncIterable[str],
    *,
    interval_s: float = 15.0,
    comment: str = "keepalive",
) -> AsyncIterator[str]:
    """
    Yield from an async iterable, emitting SSE comments when the source is idle.

    Important: This implementation avoids cancelling the underlying iterator while
    waiting (unlike `asyncio.wait_for(__anext__(), timeout=...)`, which would cancel
    the pending `__anext__` and can terminate the upstream generator).
    """
    timeout_s = float(interval_s)
    if timeout_s < 0:
        timeout_s = 0.0

    iterator = source.__aiter__()
    next_task: asyncio.Task | None = asyncio.create_task(iterator.__anext__())

    try:
        while next_task is not None:
            done, _pending = await asyncio.wait({next_task}, timeout=timeout_s)

            if next_task in done:
                try:
                    item = next_task.result()
                except StopAsyncIteration:
                    break
                yield item
                next_task = asyncio.create_task(iterator.__anext__())
                continue

            yield format_sse_comment(comment)
    finally:
        if next_task is not None and not next_task.done():
            next_task.cancel()


async def iter_abort_on_disconnect(
    source: AsyncIterable[str],
    *,
    is_disconnected: Callable[[], Awaitable[bool]],
    check_interval_s: float = 1.0,
) -> AsyncIterator[str]:
    """
    Yield from an async iterable until the client disconnects.

    This is designed for streaming endpoints (SSE/WS) where we want to stop doing
    work promptly after the client is gone, without relying on downstream tool
    code to notice cancellation immediately.
    """
    timeout_s = float(check_interval_s)
    if timeout_s < 0:
        timeout_s = 0.0

    iterator = source.__aiter__()
    next_task: asyncio.Task | None = asyncio.create_task(iterator.__anext__())

    try:
        while next_task is not None:
            done, _pending = await asyncio.wait({next_task}, timeout=timeout_s)

            if next_task in done:
                try:
                    item = next_task.result()
                except StopAsyncIteration:
                    break
                yield item
                next_task = asyncio.create_task(iterator.__anext__())
                continue

            # No source item yet; check whether the client is still connected.
            try:
                if await is_disconnected():
                    break
            except Exception:
                # Disconnect checks must never crash streams.
                continue
    finally:
        if next_task is not None and not next_task.done():
            next_task.cancel()
        try:
            aclose = getattr(iterator, "aclose", None)
            if callable(aclose):
                await aclose()
        except Exception:
            pass
