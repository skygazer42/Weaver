from types import SimpleNamespace
from unittest.mock import AsyncMock

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
async def test_health_reports_unavailable_when_the_configured_database_has_no_connection(
    monkeypatch,
):
    monkeypatch.setattr(main.settings, "database_url", "postgresql://example")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")

    assert resp.status_code == 503
    payload = resp.json()
    assert payload["database"] == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("ready", [True, False])
async def test_health_checks_database_readiness(monkeypatch, ready):
    monkeypatch.setattr(main.settings, "database_url", "postgresql://example")
    journal = SimpleNamespace(is_ready=AsyncMock(return_value=ready))
    monkeypatch.setattr(
        main.app.state, "project_streams", SimpleNamespace(journal=journal), raising=False
    )

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")

    journal.is_ready.assert_awaited_once()
    assert resp.status_code == (200 if ready else 503)
    assert resp.json()["database"] == ("configured" if ready else "unavailable")
