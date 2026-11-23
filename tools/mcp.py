import asyncio
import json
import logging
from typing import Any

from langchain.tools import BaseTool

from common.config import settings
from tools.core.mcp_clients import MCPClients

logger = logging.getLogger(__name__)

_CLIENTS: MCPClients | None = None
_CLIENTS_LOCK = asyncio.Lock()


def _parse_servers(servers: Any) -> dict[str, Any]:
    if isinstance(servers, str):
        try:
            return json.loads(servers)
        except json.JSONDecodeError:
            logger.error("MCP_SERVERS is not valid JSON; MCP tools disabled")
            return {}
    return servers or {}


async def init_mcp_tools(
    servers_override: dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> list[BaseTool]:
    """Replace the active MCP connections and return their proxy tools."""
    async with _CLIENTS_LOCK:
        await _close_mcp_tools()
        return await _init_mcp_tools(servers_override, enabled)


async def _init_mcp_tools(
    servers_override: dict[str, Any] | None, enabled: bool | None
) -> list[BaseTool]:
    global _CLIENTS
    servers_cfg = servers_override if servers_override is not None else settings.mcp_servers
    servers = _parse_servers(servers_cfg)
    use_mcp = enabled if enabled is not None else settings.enable_mcp

    if not use_mcp or not servers:
        logger.info("MCP disabled or no servers configured.")
        return []

    thread_id = servers.get("__thread_id__", "default")
    clients = MCPClients(thread_id=thread_id)
    server_items = [
        (server_id, cfg)
        for server_id, cfg in servers.items()
        if isinstance(server_id, str) and not server_id.startswith("__")
    ]
    try:
        for server_id, cfg in server_items:
            try:
                if not isinstance(cfg, dict):
                    logger.warning("Invalid MCP server config for %s, expected object", server_id)
                    continue
                if cfg.get("type") == "sse":
                    await clients.connect_sse(cfg.get("url"), server_id)
                elif cfg.get("type") == "stdio":
                    await clients.connect_stdio(cfg.get("command"), cfg.get("args", []), server_id)
                else:
                    logger.warning("Unknown MCP server type for %s", server_id)
            except Exception as e:
                logger.error("MCP connect failed for %s: %s", server_id, e)
    except asyncio.CancelledError:
        await clients.disconnect()
        raise

    _CLIENTS = clients
    logger.info("Loaded %d MCP tools from %d servers", len(clients.tools), len(server_items))
    return list(clients.tools)


async def reload_mcp_tools(
    servers_config: dict[str, Any], enabled: bool | None = None
) -> list[BaseTool]:
    return await init_mcp_tools(servers_override=servers_config, enabled=enabled)


async def close_mcp_tools() -> None:
    async with _CLIENTS_LOCK:
        await _close_mcp_tools()


async def _close_mcp_tools() -> None:
    global _CLIENTS
    if _CLIENTS is not None:
        await _CLIENTS.disconnect()
        _CLIENTS = None
