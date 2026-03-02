import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_public_config_endpoint_exposes_safe_defaults():
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/config/public")

    assert resp.status_code == 200
    payload = resp.json()

    assert payload["version"] == main.app.version
    assert payload["defaults"]["primary_model"] == main.settings.primary_model
    assert payload["defaults"]["reasoning_model"] == main.settings.reasoning_model

    assert payload["streaming"]["chat"]["protocol"] in {"sse", "legacy"}
    assert payload["streaming"]["research"]["protocol"] in {"sse", "legacy"}

    # Should not leak secrets.
    as_text = resp.text
    assert "OPENAI_API_KEY" not in as_text
    assert "E2B_API_KEY" not in as_text

