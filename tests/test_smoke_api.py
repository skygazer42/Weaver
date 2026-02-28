import os
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Force in-memory checkpointer during tests to avoid DB dependency
os.environ["DATABASE_URL"] = ""

from common.config import settings
from main import app


@pytest.mark.asyncio
async def test_chat_stream_smoke():
    """Basic smoke test for /api/chat streaming endpoint."""
    live = (os.getenv("WEAVER_LIVE_TESTS") or "").strip().lower() in {"1", "true", "yes", "y", "on"}
    if not live:
        pytest.skip("Set WEAVER_LIVE_TESTS=1 to run the live /api/chat smoke test.")

    if not settings.openai_api_key:
        pytest.skip("OPENAI_API_KEY is not configured; skipping live /api/chat smoke test.")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        model = (os.getenv("WEAVER_SMOKE_MODEL") or "").strip() or settings.primary_model
        payload = {
            "messages": [{"role": "user", "content": "Hello, just say hi."}],
            "stream": False,
            "model": model,
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


@pytest.mark.asyncio
async def test_cancel_endpoints_smoke():
    """Cancellation endpoints should never 500 for unknown threads."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/chat/cancel/test-thread-123")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") in {"cancelled", "not_found"}

        resp2 = await ac.post("/api/chat/cancel-all")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2.get("status") == "all_cancelled"

        resp3 = await ac.get("/api/tasks/active")
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert "active_tasks" in data3
        assert "stats" in data3


@pytest.mark.asyncio
async def test_interrupt_resume_unknown_thread_returns_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/interrupt/resume", json={"thread_id": "nope", "payload": {}})
        assert resp.status_code == 404
