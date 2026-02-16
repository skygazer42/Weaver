import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_chat_sse_no_key_does_not_emit_quality_update(monkeypatch):
    monkeypatch.setattr(main.settings, "openai_api_key", "")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/chat/sse",
            json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
        )

    assert resp.status_code == 200
    text = resp.text
    assert "event: error" in text
    assert "event: quality_update" not in text
