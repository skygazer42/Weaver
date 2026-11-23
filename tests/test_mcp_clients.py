import asyncio
import sys
from collections import defaultdict
from contextlib import asynccontextmanager
from textwrap import dedent
from types import SimpleNamespace

import pytest

from agent.core.events import ToolEventType
from tools import mcp
from tools.core import mcp_clients, registry


@pytest.mark.asyncio
async def test_stdio_tools_validate_arguments_and_route_events_to_each_run(tmp_path, monkeypatch):
    server = tmp_path / "read_only_mcp.py"
    server.write_text(
        dedent("""
            import json
            import sys

            for line in sys.stdin:
                request = json.loads(line)
                if "id" not in request:
                    continue
                match request["method"]:
                    case "initialize":
                        result = {
                            "protocolVersion": request["params"]["protocolVersion"],
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "read-only fixture", "version": "1.0"},
                        }
                    case "tools/list":
                        result = {"tools": [{
                            "name": "read_count",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"count": {"type": "integer"}},
                                "required": ["count"],
                            },
                        }]}
                    case "tools/call":
                        assert request["params"]["name"] == "read_count"
                        count = request["params"]["arguments"]["count"]
                        result = {"content": [{"type": "text", "text": f"count={count}"}]}
                    case method:
                        raise AssertionError(f"Unexpected MCP method {method}")
                print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
        """),
        encoding="utf-8",
    )
    owner_loop = asyncio.get_running_loop()
    call_tool = mcp_clients.ClientSession.call_tool
    forwarded = []
    closed_transports = []
    stdio_client = mcp_clients.stdio_client

    @asynccontextmanager
    async def track_stdio(parameters):
        owner = asyncio.current_task()
        async with stdio_client(parameters) as streams:
            yield streams
        assert asyncio.current_task() is owner
        closed_transports.append(owner)

    async def track_call(session, name, arguments):
        assert asyncio.get_running_loop() is owner_loop
        forwarded.append(arguments["count"])
        return await call_tool(session, name, arguments)

    events = defaultdict(list)

    def emitter(thread_id):
        return SimpleNamespace(emit_sync=lambda event_type, _: events[thread_id].append(event_type))

    monkeypatch.setattr(mcp_clients, "stdio_client", track_stdio)
    monkeypatch.setattr(mcp_clients.ClientSession, "call_tool", track_call)
    monkeypatch.setattr(mcp_clients, "get_emitter_sync", emitter)
    config = {"fixture": {"type": "stdio", "command": sys.executable, "args": [str(server)]}}

    try:
        tools = await asyncio.wait_for(mcp.init_mcp_tools(config, enabled=True), timeout=20)
        monkeypatch.setattr(registry, "_REGISTERED_TOOLS", tools)
        [first] = registry.get_registered_tools(thread_id="first")
        [second] = registry.get_registered_tools(thread_id="second")

        assert first.args_schema["properties"]["count"]["type"] == "integer"
        results = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(first.invoke, {"count": 2}), second.ainvoke({"count": 3})
            ),
            timeout=10,
        )
        assert results == ["count=2", "count=3"]
        assert events == {
            "first": [ToolEventType.TOOL_START, ToolEventType.TOOL_RESULT],
            "second": [ToolEventType.TOOL_START, ToolEventType.TOOL_RESULT],
        }

        invalid = await second.ainvoke({"count": "3"})
        assert invalid.startswith("Invalid MCP tool arguments:")
        assert sorted(forwarded) == [2, 3]
        assert events["second"][-2:] == [ToolEventType.TOOL_START, ToolEventType.TOOL_ERROR]
    finally:
        await asyncio.wait_for(mcp.close_mcp_tools(), timeout=10)
    assert len(closed_transports) == 1


@pytest.fixture
def sse_lifecycle(monkeypatch):
    closed = []

    @asynccontextmanager
    async def transport(*, url):
        owner = asyncio.current_task()
        try:
            yield (url,)
        finally:
            assert asyncio.current_task() is owner
            closed.append((url, "transport"))

    @asynccontextmanager
    async def session(url):
        owner = asyncio.current_task()

        async def initialize():
            if url.endswith("/failure"):
                raise ValueError("fixture initialization failed")

        async def list_tools():
            return SimpleNamespace(tools=[])

        try:
            yield SimpleNamespace(initialize=initialize, list_tools=list_tools)
        finally:
            assert asyncio.current_task() is owner
            closed.append((url, "session"))

    monkeypatch.setattr(mcp_clients, "sse_client", transport)
    monkeypatch.setattr(mcp_clients, "ClientSession", session)
    return closed


@pytest.mark.asyncio
async def test_sse_reload_and_shutdown_close_each_connection_on_its_owner(sse_lifecycle):
    first = {"fixture": {"type": "sse", "url": "http://fixture/first"}}
    second = {"fixture": {"type": "sse", "url": "http://fixture/second"}}
    third = {"fixture": {"type": "sse", "url": "http://fixture/third"}}
    try:
        await asyncio.create_task(mcp.init_mcp_tools(first, enabled=True))
        await asyncio.gather(
            mcp.reload_mcp_tools(second, enabled=True), mcp.reload_mcp_tools(third, enabled=True)
        )
    finally:
        await asyncio.create_task(mcp.close_mcp_tools())
    assert sse_lifecycle == [
        (config["fixture"]["url"], context)
        for config in (first, second, third)
        for context in ("session", "transport")
    ]


@pytest.mark.asyncio
async def test_failed_sse_initialization_closes_contexts_before_returning(sse_lifecycle):
    url = "http://fixture/failure"
    try:
        tools = await mcp.init_mcp_tools({"fixture": {"type": "sse", "url": url}}, enabled=True)
        assert tools == []
        assert sse_lifecycle == [(url, "session"), (url, "transport")]
    finally:
        await mcp.close_mcp_tools()
