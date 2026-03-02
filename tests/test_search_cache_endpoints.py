import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_search_cache_stats_and_clear():
    from agent.core.search_cache import get_search_cache

    cache = get_search_cache()
    cache.clear()
    cache.set("hello", [{"title": "x", "url": "https://example.com"}])

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        stats_resp = await ac.get("/api/search/cache/stats")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()["stats"]
        assert stats["size"] >= 1

        clear_resp = await ac.post("/api/search/cache/clear")
        assert clear_resp.status_code == 200
        assert clear_resp.json()["cleared"] is True

        stats_resp2 = await ac.get("/api/search/cache/stats")
        assert stats_resp2.status_code == 200
        assert stats_resp2.json()["stats"]["size"] == 0

