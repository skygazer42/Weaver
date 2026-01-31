import re

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_x_request_id_header_is_present():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")

    assert resp.status_code == 200

    request_id = resp.headers.get("x-request-id")
    assert request_id, "expected X-Request-ID header to be set"
    assert re.fullmatch(r"[0-9a-f]{8}", request_id)
