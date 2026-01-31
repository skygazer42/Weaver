"""
Evented MCP multi-server client (SSE + stdio).

- Connect/disconnect multiple MCP servers
- List and register remote tools with server-prefixed names
- Emit start/result/error events for front-end visibility
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from langchain.tools import BaseTool

from agent.core.events import ToolEventType, get_emitter_sync

logger = logging.getLogger(__name__)

try:  # Optional dependency
    from mcp import ClientSession, StdioServerParameters  # type: ignore
    from mcp.client.sse import sse_client  # type: ignore
    from mcp.client.stdio import stdio_client  # type: ignore
    from mcp.types import ListToolsResult  # type: ignore
except Exception:  # pragma: no cover
    ClientSession = None  # type: ignore
    StdioServerParameters = None  # type: ignore
    sse_client = None  # type: ignore
    stdio_client = None  # type: ignore
    ListToolsResult = None  # type: ignore


class MCPClientTool(BaseTool):
    """Proxy for a remote MCP tool; emits events on execution."""

    session: Any = None
    server_id: str = ""
    original_name: str = ""
    thread_id: str = "default"

    def _run(self, **kwargs):
        if not self.session:
            return f"Error: not connected to MCP server {self.server_id}"
        emitter = get_emitter_sync(self.thread_id)
        emitter.emit_sync(
            ToolEventType.TOOL_START, {"tool": self.name, "args": kwargs, "server": self.server_id}
        )
        try:
            result = asyncio.get_event_loop().run_until_complete(
                self.session.call_tool(self.original_name, kwargs)
            )
            content_items = getattr(result, "content", None) or []
            parts: List[str] = []
            for item in content_items:
                text = getattr(item, "text", None)
                if isinstance(text, str) and text:
                    parts.append(text)
                else:
                    parts.append(str(item))
            content = ", ".join([p for p in parts if p])
            emitter.emit_sync(
                ToolEventType.TOOL_RESULT,
                {
                    "tool": self.name,
                    "result": content or "No output",
                    "server": self.server_id,
                    "success": True,
                },
            )
            return content or "No output"
        except Exception as e:
            emitter.emit_sync(
                ToolEventType.TOOL_ERROR,
                {"tool": self.name, "error": str(e), "server": self.server_id},
            )
            return f"Error executing MCP tool: {e}"


class MCPClients:
    """Manage multiple MCP server connections and expose their tools."""

    def __init__(self, thread_id: str = "default"):
        self.sessions: Dict[str, Any] = {}
        self.exit_stacks: Dict[str, asyncio.AbstractEventLoop] = {}
        self.tools: List[BaseTool] = []
        self.thread_id = thread_id

    async def connect_sse(self, server_url: str, server_id: str = "") -> None:
        if sse_client is None or ClientSession is None:
            raise RuntimeError("Missing dependency: mcp. Install with `pip install mcp`.")
        server_id = server_id or server_url
        if server_id in self.sessions:
            await self.disconnect(server_id)

        streams_context = sse_client(url=server_url)
        streams = await streams_context.__aenter__()
        session = await ClientSession(*streams).__aenter__()
        self.sessions[server_id] = session
        self.exit_stacks[server_id] = streams_context

        await self._initialize(server_id)

    async def connect_stdio(self, command: str, args: List[str], server_id: str = "") -> None:
        if stdio_client is None or ClientSession is None or StdioServerParameters is None:
            raise RuntimeError("Missing dependency: mcp. Install with `pip install mcp`.")
        server_id = server_id or command
        if server_id in self.sessions:
            await self.disconnect(server_id)

        server_params = StdioServerParameters(command=command, args=args)
        stdio_transport = await stdio_client(server_params).__aenter__()
        read, write = stdio_transport
        session = await ClientSession(read, write).__aenter__()
        self.sessions[server_id] = session
        self.exit_stacks[server_id] = stdio_transport

        await self._initialize(server_id)

    async def _initialize(self, server_id: str) -> None:
        session = self.sessions.get(server_id)
        if not session:
            return
        await session.initialize()
        response = await session.list_tools()
        self._register_tools(response, server_id)

    def _register_tools(self, tools_result: Any, server_id: str) -> None:
        for tool in tools_result.tools:
            original_name = tool.name
            tool_name = f"mcp_{server_id}_{original_name}".replace(" ", "_")
            proxy = MCPClientTool(
                name=tool_name,
                description=tool.description,
                parameters=tool.inputSchema,
            )
            proxy.session = self.sessions.get(server_id)
            proxy.server_id = server_id
            proxy.original_name = original_name
            proxy.thread_id = self.thread_id
            self.tools.append(proxy)
        logger.info(f"[mcp] registered {len(tools_result.tools)} tools from {server_id}")

    async def disconnect(self, server_id: str = "") -> None:
        targets = [server_id] if server_id else list(self.sessions.keys())
        for sid in targets:
            session = self.sessions.pop(sid, None)
            if session:
                try:
                    await session.__aexit__(None, None, None)
                except Exception as e:
                    logger.warning(f"[mcp] closing session {sid} failed: {e}")
            ctx = self.exit_stacks.pop(sid, None)
            if ctx:
                try:
                    await ctx.__aexit__(None, None, None)
                except Exception:
                    pass
            # prune tools
            self.tools = [t for t in self.tools if getattr(t, "server_id", "") != sid]

    async def list_tools(self) -> ListToolsResult:
        tools_result = ListToolsResult(tools=[])
        for session in self.sessions.values():
            resp = await session.list_tools()
            tools_result.tools += resp.tools
        return tools_result
