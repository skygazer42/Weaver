import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_research_sse_sets_thread_header_even_on_error(monkeypatch):
    # Force deterministic error path like /api/chat/sse
    monkeypatch.setattr(main.settings, "openai_api_key", "")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/research/sse", json={"query": "hi"})
        assert resp.status_code == 200
        assert resp.headers.get("X-Thread-ID")

