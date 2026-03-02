import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_metrics_includes_streaming_connection_gauges():
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/metrics")

    assert resp.status_code == 200
    text = resp.text
    assert "weaver_sse_active_connections" in text
    assert "weaver_ws_active_connections" in text

