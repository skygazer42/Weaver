import logging

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_request_logging_includes_start_and_complete(caplog):
    caplog.set_level(logging.INFO)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")

    assert resp.status_code == 200

    messages = [r.getMessage() for r in caplog.records]
    assert any("Request started" in m and "/health" in m for m in messages)
    assert any("Request completed" in m and "/health" in m for m in messages)
