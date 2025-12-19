import pytest
from httpx import AsyncClient, ASGITransport

from main import app
from common.config import settings


@pytest.mark.asyncio
async def test_chat_stream_smoke():
    """Basic smoke test for /api/chat streaming endpoint."""
    pytest.skip("Chat smoke requires real OpenAI key; skipped in CI/local without creds.")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "messages": [{"role": "user", "content": "Hello, just say hi."}],
            "stream": False,
            "model": "gpt-4o-mini"
        }
        resp = await ac.post("/api/chat", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert isinstance(data["content"], str)


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
