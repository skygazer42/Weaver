import asyncio

import pytest

from common.sse import iter_with_sse_keepalive


@pytest.mark.asyncio
async def test_iter_with_sse_keepalive_emits_comment_when_idle():
    gate = asyncio.Event()

    async def source():
        # Block indefinitely so the keepalive path is deterministic.
        await gate.wait()
        yield "0:{\"type\":\"text\",\"data\":{\"content\":\"hi\"}}\\n"

    iterator = iter_with_sse_keepalive(source(), interval_s=0.0)
    first = await anext(iterator)
    assert first == ": keepalive\n\n"
    await iterator.aclose()


@pytest.mark.asyncio
async def test_iter_with_sse_keepalive_yields_source_items_without_inserting_comment():
    async def source():
        yield "0:{\"type\":\"status\",\"data\":{\"text\":\"ok\"}}\\n"

    iterator = iter_with_sse_keepalive(source(), interval_s=30.0)
    first = await anext(iterator)
    assert first.startswith("0:")
