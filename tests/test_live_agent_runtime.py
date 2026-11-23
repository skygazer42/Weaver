"""Opt-in SiliconFlow smoke test through the Weaver Agent HTTP route."""

import os
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import pytest
from langchain_core.tools import tool


@pytest.mark.asyncio
async def test_live_agent_http_preserves_history_and_tool_reply(monkeypatch):
    if os.getenv("WEAVER_LIVE_TESTS") != "1":
        pytest.skip("Set WEAVER_LIVE_TESTS=1 to test the configured SiliconFlow model")

    import main
    from agent.core.llm_factory import create_chat_model
    from agent.workflows import agent_factory, nodes

    settings = main.settings
    host = urlparse(settings.openai_base_url).hostname
    if host not in {"api.siliconflow.cn", "api.siliconflow.com"} or not settings.openai_api_key:
        pytest.skip("Configure a SiliconFlow endpoint and credential")

    calls = []

    @tool
    def receipt_lookup() -> str:
        """Return the receipt for the synthetic test workspace."""
        calls.append("fixture")
        return "FIXTURE-591"

    def model_factory(model, temperature=0):
        return create_chat_model(
            model,
            temperature=temperature,
            extra_body={"enable_thinking": False},
        ).bind(max_tokens=300)

    monkeypatch.setattr(settings, "internal_api_key", "")
    monkeypatch.setattr(settings, "tool_approval", False)
    monkeypatch.setattr(settings, "tool_selector", False)
    monkeypatch.setattr(settings, "enable_todo_middleware", False)
    monkeypatch.setattr(main, "_store_search", lambda *_, **__: [])
    monkeypatch.setattr(main, "fetch_memories", lambda **_: [])
    monkeypatch.setattr(main, "store_interaction", lambda *_, **__: True)
    monkeypatch.setattr(main, "_store_add", lambda *_, **__: None)
    monkeypatch.setattr(nodes, "_should_use_fast_agent_path", lambda *_: False)
    monkeypatch.setattr(nodes, "build_agent_tools", lambda _: [receipt_lookup])
    monkeypatch.setattr(agent_factory, "_build_llm", model_factory)

    conversation = [
        {"role": "user", "content": "The fixture's verification code is WEAVER-338."},
        {"role": "assistant", "content": "I have recorded the code for this conversation."},
        {
            "role": "user",
            "content": "Call receipt_lookup once and return both the receipt and my earlier verification code.",
        },
    ]
    run_id = uuid4().hex
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app),
        base_url="http://weaver-fixture",
    ) as client:
        result = await client.post(
            f"/api/chat/sse?research_id={run_id}",
            json={
                "messages": conversation,
                "search_mode": "agent",
                "conversation_id": "fixture-session",
                "model": settings.primary_model,
            },
        )
        replay = await client.get(f"/api/chat/sse/{run_id}")
    assert result.status_code == replay.status_code == 200
    assert result.headers["X-Thread-ID"] == replay.headers["X-Thread-ID"]
    assert "FIXTURE-591" in result.text and "WEAVER-338" in result.text
    assert "event: run_status" in result.text and "completed" in result.text
    assert calls == ["fixture"]
