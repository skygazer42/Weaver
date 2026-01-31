import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_health_reports_not_configured_when_database_url_missing(monkeypatch):
    monkeypatch.setattr(main.settings, "database_url", "")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["database"] == "not configured"


@pytest.mark.asyncio
async def test_health_reports_configured_when_database_url_present(monkeypatch):
    monkeypatch.setattr(main.settings, "database_url", "postgresql://example")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["database"] == "configured"
