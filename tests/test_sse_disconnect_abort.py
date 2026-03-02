import asyncio

import pytest


@pytest.mark.asyncio
async def test_iter_abort_on_disconnect_stops_iteration():
    from common.sse import iter_abort_on_disconnect

    gate = asyncio.Event()

    async def source():
        # Never yields unless gate is set; simulates a stuck/slow upstream generator.
        await gate.wait()
        yield "hello"

    calls = 0

    async def is_disconnected() -> bool:
        nonlocal calls
        calls += 1
        return True

    iterator = iter_abort_on_disconnect(source(), is_disconnected=is_disconnected, check_interval_s=0.0)

    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(iterator), timeout=1.0)

    assert calls >= 1

