import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import app


@pytest.mark.asyncio
async def test_agents_crud(tmp_path, monkeypatch):
    """
    Agents are persisted to a local JSON file. Patch the store paths so tests
    don't touch repo data/agents.json.
    """
    from agent.prompts.agent_prompts import get_default_agent_prompt
    from common import agents_store

    def _paths(_project_root=None):
        return agents_store.AgentsStorePaths(root=tmp_path, file=tmp_path / "agents.json")

    monkeypatch.setattr(agents_store, "default_store_paths", _paths)

    # Seed default agent
    agents_store.ensure_default_agent(
        default_profile=agents_store.AgentProfile(
            id="default",
            name="Default",
            description="test",
            system_prompt=get_default_agent_prompt(),
            enabled_tools={"web_search": True},
            metadata={"protected": True},
        )
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # list
        resp = await ac.get("/api/agents")
        assert resp.status_code == 200
        agents = resp.json().get("agents", [])
        assert any(a.get("id") == "default" for a in agents)

        # get default
        resp2 = await ac.get("/api/agents/default")
        assert resp2.status_code == 200
        assert resp2.json().get("id") == "default"

        # create
        create_payload = {
            "name": "My Agent",
            "description": "demo",
            "system_prompt": "You are a test agent.",
            "enabled_tools": {"web_search": True, "mcp": False},
        }
        resp3 = await ac.post("/api/agents", json=create_payload)
        assert resp3.status_code == 200
        created = resp3.json()
        created_id = created.get("id")
        assert created_id and created_id != "default"

        # update
        upd = {**create_payload, "name": "My Agent v2"}
        resp4 = await ac.put(f"/api/agents/{created_id}", json=upd)
        assert resp4.status_code == 200
        assert resp4.json().get("name") == "My Agent v2"

        # delete
        resp5 = await ac.delete(f"/api/agents/{created_id}")
        assert resp5.status_code == 200
        assert resp5.json().get("status") == "deleted"

        # deleted => 404
        resp6 = await ac.get(f"/api/agents/{created_id}")
        assert resp6.status_code == 404

        # default protected
        resp7 = await ac.delete("/api/agents/default")
        assert resp7.status_code == 400

