import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from triggers import init_trigger_manager, shutdown_trigger_manager


@pytest.mark.asyncio
async def test_webhook_trigger_endpoint_returns_json(tmp_path):
    """
    Regression test: /api/webhook/{trigger_id} should not 500 due to
    non-JSON-serializable callback results (e.g., un-awaited coroutine objects).
    """
    await shutdown_trigger_manager()
    await init_trigger_manager(storage_path=str(tmp_path / "triggers.json"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        create = await ac.post(
            "/api/triggers/webhook",
            json={
                "name": "Test Webhook",
                "description": "webhook smoke",
                "agent_id": "default",
                "task": "noop",
                "task_params": {"hello": "world"},
                "http_methods": ["POST"],
                "require_auth": False,
            },
        )
        assert create.status_code == 200
        trigger_id = create.json().get("trigger_id")
        assert trigger_id

        fired = await ac.post(f"/api/webhook/{trigger_id}", json={"ping": "pong"})
        assert fired.status_code == 200
        data = fired.json()
        assert data.get("success") is True

    await shutdown_trigger_manager()

