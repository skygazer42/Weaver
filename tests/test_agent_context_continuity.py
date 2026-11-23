import asyncio
from types import SimpleNamespace

import pytest
from fastapi import Request
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from agent.core.state import capped_add_messages
from agent.workflows import agent_factory, agent_tools, nodes
from common.config import Settings
from common.tool_artifacts import save_tool_artifact
from tools.core import mcp_clients, registry


@pytest.mark.asyncio
async def test_chat_turn_forwards_history_and_writes_memory_once_per_owner(monkeypatch):
    import main

    captured = []
    stored = []

    class Graph:
        async def astream_events(self, state, config):
            captured.append((state, config))
            for _ in range(2):
                yield {
                    "event": "on_chain_end",
                    "name": "fixture",
                    "data": {"output": {"is_complete": True, "final_report": "A fixture answer"}},
                }

        async def ainvoke(self, state, config):
            captured.append((state, config))
            return {"final_report": "A fixture answer"}

    monkeypatch.setattr(main, "research_graph", Graph())
    monkeypatch.setattr(main.settings, "internal_api_key", "fixture")
    monkeypatch.setattr(main.settings, "openai_api_key", "fixture")
    monkeypatch.setattr(main, "_store_search", lambda *_, **__: ["A reference fact"])
    monkeypatch.setattr(main, "fetch_memories", lambda **_: [])
    monkeypatch.setattr(main, "_store_add", lambda *_, **__: None)
    monkeypatch.setattr(main, "add_memory_entry", lambda *_, **__: True, raising=False)
    monkeypatch.setattr(
        main, "store_interaction", lambda _, __, user_id=None: stored.append(user_id)
    )

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    for endpoint, stream in ((main.chat, True), (main.chat_sse, True), (main.chat, False)):
        request = Request({"type": "http", "state": {"principal_id": "fixture-owner"}}, receive)
        response = await endpoint(
            request,
            main.ChatRequest(
                messages=[
                    {"role": "system", "content": "Client-side system text"},
                    {"role": "user", "content": "My label is elm-23."},
                    {"role": "assistant", "content": "I have the label."},
                    {"role": "user", "content": "What label did I give?"},
                ],
                search_mode="agent",
                conversation_id="fixture-session",
                stream=stream,
            ),
        )
        if stream:
            async for _ in response.body_iterator:
                pass

    assert len(captured) == 3
    for state, _ in captured:
        assert state["input"] == "What label did I give?"
        assert state["conversation_id"] == "fixture-session"
        assert "My label is elm-23." in [item.content for item in state["messages"]]
        assert "I have the label." in [item.content for item in state["messages"]]
        assert all(item.content != "Client-side system text" for item in state["messages"])
        assert not any(
            isinstance(item, SystemMessage) and "A reference fact" in item.content
            for item in state["messages"]
        )
    assert stored == ["fixture-owner"] * 3


def test_agent_keeps_base_instructions_with_seeded_context(monkeypatch):
    from agent.prompts import system_prompts

    received = []

    class Agent:
        def invoke(self, state, config):
            received.append(state["messages"])
            return {"messages": [AIMessage("A fixture answer")]}

    monkeypatch.setattr(nodes, "_should_use_fast_agent_path", lambda *_: False)
    monkeypatch.setattr(nodes, "build_agent_tools", lambda _: [])
    monkeypatch.setattr(nodes, "build_tool_agent", lambda **_: Agent())
    monkeypatch.setattr(system_prompts, "get_agent_prompt", lambda **_: "Base fixture instructions")
    config = {
        "configurable": {
            "model": "fixture",
            "thread_id": "fixture-thread",
            "agent_profile": {"browser_context_helper": False},
        }
    }
    nodes.agent_node({"input": "A fixture question", "messages": []}, config)
    nodes.agent_node(
        {"input": "Another question", "messages": [SystemMessage("Profile context")]}, config
    )
    base_system = received[0][0].content
    assert any(
        base_system in item.content for item in received[1] if isinstance(item, SystemMessage)
    )
    assert any("Profile context" in item.content for item in received[1])


@pytest.mark.asyncio
async def test_mcp_tools_use_connection_loop_and_own_run_events(monkeypatch):
    loop = asyncio.get_running_loop()
    routes = []

    class Session:
        async def call_tool(self, name, arguments):
            assert asyncio.get_running_loop() is loop
            return SimpleNamespace(content=[SimpleNamespace(text=arguments["value"])])

    def emitter(thread_id):
        routes.append(thread_id)
        return SimpleNamespace(emit_sync=lambda *_: None)

    monkeypatch.setattr(mcp_clients, "get_emitter_sync", emitter)
    shared = mcp_clients.MCPClientTool(
        name="mcp_fixture_echo",
        description="Synthetic read-only tool",
        original_name="echo",
        session=Session(),
        connection_loop=loop,
        args_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
    )
    monkeypatch.setattr(registry, "_REGISTERED_TOOLS", [shared])
    monkeypatch.setattr(agent_tools.settings, "sandbox_mode", "local")

    def build(thread):
        disabled = {
            name: False
            for name in (
                "web_search",
                "crawl",
                "task_list",
                "ask_human",
                "str_replace",
                "planning",
                "browser_use",
            )
        }
        tools = agent_tools.build_agent_tools(
            {
                "configurable": {
                    "thread_id": thread,
                    "agent_profile": {"enabled_tools": disabled, "emit_tool_events": False},
                }
            }
        )
        return next(item for item in tools if item.name == "mcp_fixture_echo")

    first, second = build("first"), build("second")
    assert (
        first.thread_id == "first"
        and second.thread_id == "second"
        and shared.thread_id == "default"
    )
    answers = await asyncio.gather(
        asyncio.to_thread(first.invoke, {"value": "sync"}), second.ainvoke({"value": "async"})
    )
    assert answers == ["sync", "async"]
    assert sorted(routes) == ["first", "second"]


def test_large_tool_result_can_be_read_in_pages(monkeypatch):
    output = "fixture payload " * 5000 + "TAIL"
    seen = []

    @tool
    def fixture_output() -> str:
        """Return a long synthetic result."""
        return output

    class Chat(BaseChatModel):
        @property
        def _llm_type(self):
            return "fixture-agent"

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            replies = [message for message in messages if isinstance(message, ToolMessage)]
            if not replies:
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "fixture_output",
                            "args": {},
                            "id": "original",
                            "type": "tool_call",
                        }
                    ],
                )
            elif len(replies) == 1:
                seen.append(replies[0])
                message = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_tool_result",
                            "args": {"artifact_id": "original", "offset": len(output) - 4},
                            "id": "reader",
                            "type": "tool_call",
                        }
                    ],
                )
            else:
                seen.append(replies[-1])
                message = AIMessage("done")
            return ChatResult(generations=[ChatGeneration(message=message)])

    settings = Settings(
        _env_file=None,
        enable_todo_middleware=False,
        tool_selector=False,
        tool_retry=False,
        tool_call_limit=0,
        strip_tool_messages=False,
        tool_approval=False,
    )
    monkeypatch.setattr(agent_factory, "_build_llm", lambda *_, **__: Chat())
    monkeypatch.setattr(agent_factory, "settings", settings)
    agent = agent_factory.build_tool_agent(model="fixture", tools=[fixture_output])
    agent.invoke({"messages": [HumanMessage("Use the fixture")]})
    assert len(seen[0].content) < 7000
    assert "read_tool_result" in seen[0].content
    assert "TAIL" in seen[1].content


def test_history_retains_call_and_all_replies_at_trim_boundary(monkeypatch):
    from common.config import settings

    monkeypatch.setattr(settings, "trim_messages", True)
    monkeypatch.setattr(settings, "trim_messages_keep_first", 1)
    monkeypatch.setattr(settings, "trim_messages_keep_last", 1)
    monkeypatch.setattr(settings, "summary_messages", False)
    monkeypatch.setattr(settings, "strip_tool_messages", True)
    call = AIMessage(
        content="",
        tool_calls=[
            {"name": "one", "id": "call-one", "args": {}, "type": "tool_call"},
            {"name": "two", "id": "call-two", "args": {}, "type": "tool_call"},
        ],
    )
    result = capped_add_messages(
        [SystemMessage("Fixture instructions"), HumanMessage("Use both tools")],
        [
            call,
            ToolMessage("one", tool_call_id="call-one"),
            ToolMessage("two", tool_call_id="call-two"),
        ],
    )
    assert isinstance(result[-3], AIMessage)
    assert [item.tool_call_id for item in result[-2:]] == ["call-one", "call-two"]
    assert all(item.content == "[Tool result omitted]" for item in result[-2:])


@pytest.mark.asyncio
async def test_artifact_download_is_scoped_to_the_authenticated_owner(tmp_path, monkeypatch):
    import main

    monkeypatch.setenv("WEAVER_DATA_DIR", str(tmp_path))
    artifact = save_tool_artifact("thread-one", "owner-one", "tool-call", "fixture payload")
    received = await main.download_tool_artifact(
        artifact.id,
        Request({"type": "http", "state": {"principal_id": "owner-one"}}),
    )
    assert received.body == b"fixture payload"
    with pytest.raises(main.HTTPException) as denied:
        await main.download_tool_artifact(
            artifact.id,
            Request({"type": "http", "state": {"principal_id": "owner-two"}}),
        )
    assert denied.value.status_code == 404


def test_bundle_exposes_skill_metadata_and_reads_selected_recipe():
    from agent.workflows.agent_skills import read_skill, skill_catalog

    assert "sandbox" in skill_catalog()["csv-analysis"]
    recipe = read_skill.invoke({"name": "csv-analysis"})
    assert "name: csv-analysis" in recipe


def test_model_budget_keeps_recent_tool_replies_and_references_older_artifacts():
    from langchain.agents.middleware.types import ModelRequest

    from agent.workflows.tool_results import _prepare_model_request, read_tool_result

    model = SimpleNamespace(profile={"max_input_tokens": 800}, max_tokens=200)
    older = ToolMessage("x" * 4000, tool_call_id="earlier", artifact={"weaver_full_tool_result": "complete"})
    recent = ToolMessage("recent result", tool_call_id="recent")
    request = ModelRequest(
        model=model, tools=[read_tool_result],
        messages=[HumanMessage("Fixture"), older, AIMessage("Continue"), recent],
    )
    prepared = _prepare_model_request(request)
    assert "artifact_id=earlier" in prepared.messages[1].content
    assert prepared.messages[1].artifact == older.artifact
    assert prepared.messages[-1] == recent


def test_single_configured_search_engine_is_used_in_agent_and_fast_path(monkeypatch):
    from common.config import settings
    from tools.search import multi_search

    calls = []

    def search(query, max_results):
        calls.append((query, max_results))
        return [
            SimpleNamespace(to_dict=lambda: {"title": "Fixture", "url": "https://example.invalid/"})
        ]

    monkeypatch.setattr(settings, "search_engines", "duckduckgo")
    monkeypatch.setattr(settings, "tool_retry", False)
    monkeypatch.setattr(
        multi_search,
        "get_search_orchestrator",
        lambda: SimpleNamespace(
            get_available_providers=lambda: [SimpleNamespace(name="duckduckgo", search=search)],
        ),
    )
    tools = agent_tools.build_agent_tools(
        {
            "configurable": {
                "thread_id": "fixture",
                "agent_profile": {"emit_tool_events": False},
            }
        }
    )
    fallback = next(item for item in tools if item.name == "fallback_search")
    assert not any(item.name == "tavily_search" for item in tools)
    assert fallback.invoke({"query": "configured search"})[0]["title"] == "Fixture"
    engine, results = nodes._run_fast_agent_search("fast search", {})
    assert engine == "duckduckgo" and results[0]["title"] == "Fixture"
    assert [query for query, _ in calls] == ["configured search", "fast search"]
