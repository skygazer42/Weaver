import json
import asyncio

import pytest
from httpx import AsyncClient

from main import app


@pytest.mark.asyncio
async def test_chat_stream_smoke():
    """Basic smoke test for /api/chat streaming endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
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
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
