import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.mark.asyncio
async def test_export_templates_endpoint_is_reachable():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/export/templates")

    assert resp.status_code == 200
    payload = resp.json()
    assert isinstance(payload.get("templates"), list)
    assert any(t.get("id") == "default" for t in payload["templates"])
