import json
import logging
from typing import List, Any, Dict

from langchain_core.tools import BaseTool
from config import settings

logger = logging.getLogger(__name__)

_CLIENT: Any = None
_TOOLS: List[BaseTool] = []


async def init_mcp_tools() -> List[BaseTool]:
    global _CLIENT, _TOOLS

    if not settings.enable_mcp or not settings.mcp_servers:
        logger.info("MCP disabled or no servers configured.")
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except Exception:
        logger.warning("langchain-mcp-adapters not installed; MCP tools disabled")
        return []

    if _CLIENT is not None and _TOOLS:
        return _TOOLS

    servers: Dict[str, Any] = settings.mcp_servers
    if isinstance(servers, str):
        try:
            servers = json.loads(servers)
        except json.JSONDecodeError:
            logger.error("MCP_SERVERS is not valid JSON; MCP tools disabled")
            return []

    _CLIENT = MultiServerMCPClient(servers)
    try:
        _TOOLS = await _CLIENT.get_tools()
    except Exception as e:
        logger.error(f"Failed to load MCP tools: {e}")
        return []

    logger.info(f"Loaded {len(_TOOLS)} MCP tools from {len(servers)} servers")
    # Log a preview of tool names
    try:
        names = [t.name for t in _TOOLS if hasattr(t, "name")]
        logger.debug(f"MCP tools: {names[:10]}")
    except Exception:
        pass
    return _TOOLS


async def close_mcp_tools() -> None:
    global _CLIENT
    if _CLIENT is None:
        return
    if hasattr(_CLIENT, "close"):
        await _CLIENT.close()
    _CLIENT = None
