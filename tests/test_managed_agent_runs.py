import json
import re
from uuid import uuid4

import httpx
import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agent.core.state import AgentState


@pytest.fixture
def local_graph(monkeypatch):
    import main

    saver = MemorySaver()
    monkeypatch.setattr(main, "checkpointer", saver)
    monkeypatch.setattr(main, "durable_streams", None)
    monkeypatch.setattr(main.settings, "openai_api_key", "fixture")
    monkeypatch.setattr(main.settings, "internal_api_key", "")
    monkeypatch.setattr(main, "_store_search", lambda *_, **__: [])
    monkeypatch.setattr(main, "fetch_memories", lambda **_: [])
    monkeypatch.setattr(main, "store_interaction", lambda *_, **__: True)
    monkeypatch.setattr(main, "_store_add", lambda *_, **__: None)

    def bind(node, name):
        graph = StateGraph(AgentState)
        graph.add_node(name, node)
        graph.add_edge(START, name)
        graph.add_edge(name, END)
        monkeypatch.setattr(main, "research_graph", graph.compile(checkpointer=saver))
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://weaver-fixture"
        )

    return bind


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [True, False])
async def test_approval_and_refusal_replay_the_same_run_once(local_graph, approved):
    executions = []

    def tool_node(state):
        answer = interrupt(
            {
                "action_requests": [{"name": "fixture_tool", "args": {"value": "verified"}}],
                "review_configs": [
                    {"action_name": "fixture_tool", "allowed_decisions": ["approve", "reject"]}
                ],
            }
        )
        if answer["decisions"][0]["type"] == "approve":
            executions.append(state["input"])
            report = "Fixture executed"
        else:
            report = "Fixture declined"
        return {"is_complete": True, "final_report": report}

    run_id = uuid4().hex
    async with local_graph(tool_node, "agent") as client:
        original = await client.post(
            f"/api/chat/sse?research_id={run_id}",
            json={
                "messages": [{"role": "user", "content": "Fixture request"}],
                "search_mode": "agent",
            },
        )
        thread = original.headers["X-Thread-ID"]
        assert "event: interrupt" in original.text and "awaiting_approval" in original.text
        redisplay = await client.get(f"/api/chat/sse/{run_id}")
        assert "event: interrupt" in redisplay.text
        events = [
            json.loads(line[6:])
            for line in redisplay.text.splitlines()
            if line.startswith("data: ")
        ]
        held = next(event["data"] for event in events if event["type"] == "interrupt")
        after = max(map(int, re.findall(r"^id: (\d+)$", redisplay.text, re.MULTILINE)))
        payload = {
            "thread_id": thread,
            "payload": {
                "tool_approved": approved,
                "tool_calls": [{"name": "fixture_tool", "args": {"value": "verified"}}],
                "interrupt_ids": held["interrupt_ids"],
            },
        }
        stale = {
            **payload,
            "payload": {**payload["payload"], "interrupt_ids": ["expired-fixture-id"]},
        }
        assert (await client.post("/api/interrupt/resume", json=stale)).status_code == 409
        for _ in range(2):
            response = await client.post("/api/interrupt/resume", json=payload)
            assert response.status_code == 202
        final = await client.get(f"/api/chat/sse/{run_id}", headers={"Last-Event-ID": str(after)})
    assert final.headers["X-Thread-ID"] == thread
    assert "Fixture executed" in final.text if approved else "Fixture declined" in final.text
    assert len(executions) == int(approved)


@pytest.mark.asyncio
async def test_empty_research_ends_as_insufficient_evidence(local_graph):
    def empty_search(state):
        return {
            "route": "deep",
            "scraped_content": [],
            "is_complete": True,
            "final_report": "No results",
        }

    async with local_graph(empty_search, "deepsearch") as client:
        response = await client.post(
            f"/api/chat/sse?research_id={uuid4().hex}",
            json={
                "messages": [{"role": "user", "content": "Fixture verification"}],
                "search_mode": "deep",
            },
        )
    assert response.status_code == 200
    assert "event: insufficient_evidence" in response.text
    assert "event: completion" not in response.text
