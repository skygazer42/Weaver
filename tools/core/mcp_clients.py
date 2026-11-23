"""
Evented MCP multi-server client (SSE + stdio).

- Connect/disconnect multiple MCP servers
- List and register remote tools with server-prefixed names
- Emit start/result/error events for front-end visibility
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from jsonschema import ValidationError, validate
from langchain.tools import BaseTool
from pydantic import Field
from referencing import Registry

from agent.core.events import ToolEventType, get_emitter_sync

logger = logging.getLogger(__name__)

try:  # Optional dependency
    from mcp import ClientSession, StdioServerParameters  # type: ignore
    from mcp.client.sse import sse_client  # type: ignore
    from mcp.client.stdio import stdio_client  # type: ignore
    from mcp.types import ListToolsResult  # type: ignore
except ImportError:  # pragma: no cover
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
    connection_loop: asyncio.AbstractEventLoop | None = Field(default=None, exclude=True)

    def _run(self, **kwargs):
        loop = self.connection_loop
        if loop is None or not loop.is_running():
            return f"Error: MCP connection for {self.server_id} is unavailable"
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is loop:
            return "Error: use the asynchronous MCP tool on its connection event loop"
        return asyncio.run_coroutine_threadsafe(self._call(kwargs), loop).result()

    async def _arun(self, **kwargs):
        loop = self.connection_loop
        if loop is None or not loop.is_running():
            return f"Error: MCP connection for {self.server_id} is unavailable"
        if loop is asyncio.get_running_loop():
            return await self._call(kwargs)
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(self._call(kwargs), loop))

    async def _call(self, arguments: dict[str, Any]) -> str:
        if self.session is None:
            return f"Error: not connected to MCP server {self.server_id}"
        emitter = get_emitter_sync(self.thread_id)
        emitter.emit_sync(
            ToolEventType.TOOL_START,
            {"tool": self.name, "args": arguments, "server": self.server_id},
        )
        try:
            if isinstance(self.args_schema, dict):
                # The remote schema can resolve local references without fetching external URLs.
                validate(arguments, self.args_schema, registry=Registry())
            result = await self.session.call_tool(self.original_name, arguments)
            content_items = getattr(result, "content", None) or []
            parts: list[str] = []
            for item in content_items:
                text = getattr(item, "text", None)
                if isinstance(text, str) and text:
                    parts.append(text)
                else:
                    parts.append(str(item))
            content = ", ".join([p for p in parts if p])
            if getattr(result, "isError", False):
                emitter.emit_sync(
                    ToolEventType.TOOL_ERROR,
                    {"tool": self.name, "error": content, "server": self.server_id},
                )
                return content or "MCP tool failed"
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
        except ValidationError as e:
            error = f"Invalid MCP tool arguments: {e.message}"
            emitter.emit_sync(
                ToolEventType.TOOL_ERROR,
                {"tool": self.name, "error": error, "server": self.server_id},
            )
            return error
        except Exception as e:
            emitter.emit_sync(
                ToolEventType.TOOL_ERROR,
                {"tool": self.name, "error": str(e), "server": self.server_id},
            )
            return f"Error executing MCP tool: {e}"


@dataclass
class _MCPConnection:
    session: Any
    task: asyncio.Task[None]
    stop: asyncio.Event


class MCPClients:
    """Manage multiple MCP server connections and expose their tools."""

    def __init__(self, thread_id: str = "default"):
        self._connections: dict[str, _MCPConnection] = {}
        self.tools: list[MCPClientTool] = []
        self.thread_id = thread_id

    async def connect_sse(self, server_url: str, server_id: str = "") -> None:
        if sse_client is None or ClientSession is None:
            raise RuntimeError("Missing dependency: mcp. Install with `pip install mcp`.")
        await self._connect(server_id or server_url, sse_client(url=server_url))

    async def connect_stdio(self, command: str, args: list[str], server_id: str = "") -> None:
        if stdio_client is None or ClientSession is None or StdioServerParameters is None:
            raise RuntimeError("Missing dependency: mcp. Install with `pip install mcp`.")
        server_params = StdioServerParameters(command=command, args=args)
        await self._connect(server_id or command, stdio_client(server_params))

    async def _connect(self, server_id: str, transport: AbstractAsyncContextManager[Any]) -> None:
        if server_id in self._connections:
            await self.disconnect(server_id)

        loop = asyncio.get_running_loop()
        ready: asyncio.Future[tuple[Any, list[MCPClientTool]]] = loop.create_future()
        stop = asyncio.Event()
        task = asyncio.create_task(self._run_connection(server_id, transport, ready, stop))
        try:
            session, tools = await ready
        except asyncio.CancelledError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        self._connections[server_id] = _MCPConnection(session, task, stop)
        self.tools.extend(tools)
        logger.info("[mcp] registered %d tools from %s", len(tools), server_id)

    async def _run_connection(
        self,
        server_id: str,
        transport: AbstractAsyncContextManager[Any],
        ready: asyncio.Future[tuple[Any, list[MCPClientTool]]],
        stop: asyncio.Event,
    ) -> None:
        try:
            # MCP's AnyIO cancel scopes must close in the same task that entered them.
            async with transport as streams, ClientSession(*streams) as session:
                await session.initialize()
                response = await session.list_tools()
                loop = asyncio.get_running_loop()
                tools = [
                    MCPClientTool(
                        name=f"mcp_{server_id}_{tool.name}".replace(" ", "_"),
                        description=tool.description or tool.name,
                        args_schema=tool.inputSchema,
                        connection_loop=loop,
                        session=session,
                        server_id=server_id,
                        original_name=tool.name,
                        thread_id=self.thread_id,
                    )
                    for tool in response.tools
                ]
                ready.set_result((session, tools))
                await stop.wait()
        except asyncio.CancelledError:
            ready.cancel()
            raise
        except Exception as e:
            if ready.done():
                logger.exception("[mcp] connection %s failed", server_id)
            else:
                ready.set_exception(e)

    async def disconnect(self, server_id: str = "") -> None:
        connections = {
            sid: connection
            for sid, connection in self._connections.items()
            if not server_id or sid == server_id
        }
        self.tools = [tool for tool in self.tools if tool.server_id not in connections]
        for connection in connections.values():
            connection.stop.set()
        await asyncio.shield(
            asyncio.gather(*(connection.task for connection in connections.values()))
        )
        for sid, connection in connections.items():
            if self._connections.get(sid) is connection:
                del self._connections[sid]

    async def list_tools(self) -> ListToolsResult:
        tools_result = ListToolsResult(tools=[])
        for connection in self._connections.values():
            resp = await connection.session.list_tools()
            tools_result.tools += resp.tools
        return tools_result
