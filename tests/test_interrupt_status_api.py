import uuid
from typing_extensions import TypedDict

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import interrupt


class StatusState(TypedDict, total=False):
    foo: str


def _make_interrupt_checkpoint(*, thread_id: str):
    # Use the same checkpointer instance as the FastAPI app so the status endpoint
    # can observe pending interrupt writes.
    from main import checkpointer

    def node(state: StatusState):
        interrupt(
            {
                "checkpoint": "status_test",
                "instruction": "Do you approve?",
                "content": "hello",
            }
        )
        return {"foo": "unreachable"}

    builder = StateGraph(StatusState)
    builder.add_node("node", node)
    builder.add_edge(START, "node")
    builder.add_edge("node", END)
    graph = builder.compile(checkpointer=checkpointer)
    graph.invoke({}, {"configurable": {"thread_id": thread_id}, "recursion_limit": 10})


@pytest.mark.asyncio
async def test_interrupt_status_returns_prompts_for_hanging_interrupt():
    from main import app

    thread_id = f"status-{uuid.uuid4().hex}"
    _make_interrupt_checkpoint(thread_id=thread_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/api/interrupt/{thread_id}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("thread_id") == thread_id
        assert data.get("is_interrupted") is True
        prompts = data.get("prompts")
        assert isinstance(prompts, list) and prompts, prompts
        assert isinstance(prompts[0], dict)
        assert prompts[0].get("checkpoint") == "status_test"

