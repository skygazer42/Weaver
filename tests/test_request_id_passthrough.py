import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_x_request_id_is_passthrough_when_provided():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health", headers={"X-Request-ID": "client-id-123"})

    assert resp.status_code == 200
    assert resp.headers.get("x-request-id") == "client-id-123"

