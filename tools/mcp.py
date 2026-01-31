import json
import logging
from typing import Any, Dict, List, Optional

from langchain.tools import BaseTool

from common.config import settings
from tools.core.mcp_clients import MCPClients

logger = logging.getLogger(__name__)

_CLIENTS: Optional[MCPClients] = None


def _parse_servers(servers: Any) -> Dict[str, Any]:
    if isinstance(servers, str):
        try:
            return json.loads(servers)
        except json.JSONDecodeError:
            logger.error("MCP_SERVERS is not valid JSON; MCP tools disabled")
            return {}
    return servers or {}


async def init_mcp_tools(
    servers_override: Optional[Dict[str, Any]] = None,
    enabled: Optional[bool] = None,
) -> List[BaseTool]:
    """
    Initialize MCP tools with evented proxy tools.
    """
    global _CLIENTS
    servers_cfg = servers_override if servers_override is not None else settings.mcp_servers
    servers: Dict[str, Any] = _parse_servers(servers_cfg)
    use_mcp = enabled if enabled is not None else settings.enable_mcp

    if not use_mcp or not servers:
        logger.info("MCP disabled or no servers configured.")
        _CLIENTS = None
        return []

    thread_id = servers.get("__thread_id__", "default")
    clients = MCPClients(thread_id=thread_id)
    for server_id, cfg in servers.items():
        try:
            if cfg.get("type") == "sse":
                await clients.connect_sse(cfg.get("url"), server_id)
            elif cfg.get("type") == "stdio":
                await clients.connect_stdio(cfg.get("command"), cfg.get("args", []), server_id)
            else:
                logger.warning(f"Unknown MCP server type for {server_id}")
        except Exception as e:
            logger.error(f"MCP connect failed for {server_id}: {e}")

    _CLIENTS = clients
    logger.info(f"Loaded {len(clients.tools)} MCP tools from {len(servers)} servers")
    return clients.tools


async def reload_mcp_tools(
    servers_config: Dict[str, Any], enabled: Optional[bool] = None
) -> List[BaseTool]:
    await close_mcp_tools()
    return await init_mcp_tools(servers_override=servers_config, enabled=enabled)


async def close_mcp_tools() -> None:
    global _CLIENTS
    if _CLIENTS is None:
        return
    try:
        await _CLIENTS.disconnect()
    finally:
        _CLIENTS = None
