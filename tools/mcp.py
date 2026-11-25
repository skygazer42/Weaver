import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from langchain.tools import BaseTool

from common.config import settings
from tools.core.mcp_clients import MCPClients

logger = logging.getLogger(__name__)

_CLIENTS: MCPClients | None = None
_CLIENTS_LOCK = asyncio.Lock()
_SERVER_STATUSES: list[dict[str, Any]] = []

DEFAULT_CONNECT_TIMEOUT_S = 20.0

_TRANSPORT_ALIASES = {
    "streamable_http": "streamable_http",
    "streamable-http": "streamable_http",
    "streamablehttp": "streamable_http",
    "http": "streamable_http",
    "sse": "sse",
    "stdio": "stdio",
}


def get_mcp_config_path() -> Path:
    raw = (getattr(settings, "mcp_config_path", "") or "config/mcp.json").strip()
    return Path(raw)


def _parse_servers_raw(servers: Any) -> dict[str, Any]:
    if isinstance(servers, str):
        raw = servers.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("MCP_SERVERS is not valid JSON; MCP tools disabled")
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return dict(servers) if isinstance(servers, dict) else {}


def infer_transport(cfg: dict[str, Any]) -> str:
    explicit = cfg.get("type") or cfg.get("transport")
    if isinstance(explicit, str) and explicit.strip():
        normalized = _TRANSPORT_ALIASES.get(explicit.strip().lower())
        if normalized:
            return normalized
        return explicit.strip().lower()
    url = cfg.get("url")
    if isinstance(url, str) and url.strip():
        clean_url = url.strip().split("?", 1)[0].rstrip("/").lower()
        if clean_url.endswith("/sse"):
            return "sse"
        return "streamable_http"
    command = cfg.get("command")
    if isinstance(command, str) and command.strip():
        return "stdio"
    return "unknown"


def normalize_server_entry(cfg: dict[str, Any]) -> dict[str, Any]:
    transport = infer_transport(cfg)
    normalized: dict[str, Any] = {"type": transport}
    if "enabled" in cfg:
        normalized["enabled"] = bool(cfg["enabled"])
    else:
        normalized["enabled"] = True

    if transport == "stdio":
        if isinstance(cfg.get("command"), str):
            normalized["command"] = cfg["command"].strip()
        args = cfg.get("args")
        normalized["args"] = [str(a) for a in args] if isinstance(args, list) else []
        env = cfg.get("env")
        if isinstance(env, dict) and env:
            normalized["env"] = {str(k): str(v) for k, v in env.items()}
        cwd = cfg.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            normalized["cwd"] = cwd.strip()
    elif transport in {"streamable_http", "sse"}:
        if isinstance(cfg.get("url"), str):
            normalized["url"] = cfg["url"].strip()
        headers = cfg.get("headers")
        if isinstance(headers, dict) and headers:
            normalized["headers"] = {str(k): str(v) for k, v in headers.items()}
    else:
        for key, value in cfg.items():
            if key not in {"type", "transport", "enabled"}:
                normalized[key] = value

    timeout = cfg.get("timeout")
    if isinstance(timeout, (int, float)) and timeout > 0:
        normalized["timeout"] = float(timeout)
    return normalized


def normalize_mcp_servers(servers: Any) -> dict[str, dict[str, Any]]:
    """Normalize standard `{mcpServers: {...}}` or flat `{id: {...}}` configs."""
    parsed = _parse_servers_raw(servers)
    inner = parsed.get("mcpServers") if isinstance(parsed.get("mcpServers"), dict) else parsed
    normalized: dict[str, dict[str, Any]] = {}
    for server_id, cfg in inner.items():
        if not isinstance(server_id, str) or server_id.startswith("__"):
            continue
        clean_id = server_id.strip()
        if not clean_id or not isinstance(cfg, dict):
            continue
        normalized[clean_id] = normalize_server_entry(cfg)
    return normalized


def load_persisted_mcp_config() -> tuple[bool, dict[str, dict[str, Any]]]:
    """Load MCP config from `config/mcp.json`, falling back to `.env` settings."""
    path = get_mcp_config_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                servers = normalize_mcp_servers(data)
                enabled = bool(data["enabled"]) if "enabled" in data else bool(servers)
                return enabled, servers
        except Exception as e:
            logger.warning("Failed to read %s: %s; falling back to env settings", path, e)
    return bool(settings.enable_mcp), normalize_mcp_servers(settings.mcp_servers)


def save_persisted_mcp_config(enabled: bool, servers: Any) -> dict[str, dict[str, Any]]:
    """Persist normalized MCP config to `config/mcp.json` using standard `mcpServers` key."""
    normalized = normalize_mcp_servers(servers)
    path = get_mcp_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled": bool(enabled),
        "mcpServers": normalized,
    }
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    return normalized


def get_mcp_server_statuses() -> list[dict[str, Any]]:
    """Return latest per-server connection status and discovered tool metadata."""
    return [dict(item) for item in _SERVER_STATUSES]


async def init_mcp_tools(
    servers_override: dict[str, Any] | str | None = None,
    enabled: bool | None = None,
    thread_id: str | None = None,
) -> list[BaseTool]:
    """Replace the active MCP connections and return their proxy tools."""
    async with _CLIENTS_LOCK:
        await _close_mcp_tools()
        return await _init_mcp_tools(servers_override, enabled, thread_id)


async def _init_mcp_tools(
    servers_override: dict[str, Any] | str | None,
    enabled: bool | None,
    thread_id: str | None = None,
) -> list[BaseTool]:
    global _CLIENTS, _SERVER_STATUSES
    if servers_override is None and enabled is None:
        persisted_enabled, normalized_servers = load_persisted_mcp_config()
        use_mcp = persisted_enabled
        effective_thread_id = thread_id or "default"
    else:
        raw_cfg = servers_override if servers_override is not None else settings.mcp_servers
        parsed_raw = _parse_servers_raw(raw_cfg)
        effective_thread_id = thread_id or str(parsed_raw.get("__thread_id__") or "default")
        normalized_servers = normalize_mcp_servers(parsed_raw)
        use_mcp = enabled if enabled is not None else settings.enable_mcp

    statuses: list[dict[str, Any]] = []

    if not use_mcp or not normalized_servers:
        for server_id, cfg in normalized_servers.items():
            statuses.append(
                {
                    "id": server_id,
                    "type": cfg.get("type", "unknown"),
                    "enabled": bool(cfg.get("enabled", True)),
                    "status": "disabled",
                    "error": None,
                    "tool_count": 0,
                    "tools": [],
                }
            )
        _SERVER_STATUSES = statuses
        logger.info("MCP disabled or no servers configured.")
        return []

    clients = MCPClients(thread_id=effective_thread_id)
    try:
        for server_id, cfg in normalized_servers.items():
            transport = cfg.get("type", "unknown")
            if not cfg.get("enabled", True):
                statuses.append(
                    {
                        "id": server_id,
                        "type": transport,
                        "enabled": False,
                        "status": "disabled",
                        "error": None,
                        "tool_count": 0,
                        "tools": [],
                    }
                )
                continue

            timeout = float(cfg.get("timeout") or DEFAULT_CONNECT_TIMEOUT_S)
            try:
                if transport == "streamable_http":
                    url = cfg.get("url")
                    if not url:
                        raise ValueError("Missing required field 'url' for streamable_http server")
                    server_tools = await clients.connect_streamable_http(
                        url,
                        server_id=server_id,
                        headers=cfg.get("headers"),
                        timeout=timeout,
                    )
                elif transport == "sse":
                    url = cfg.get("url")
                    if not url:
                        raise ValueError("Missing required field 'url' for sse server")
                    server_tools = await clients.connect_sse(
                        url,
                        server_id=server_id,
                        headers=cfg.get("headers"),
                        timeout=timeout,
                    )
                elif transport == "stdio":
                    command = cfg.get("command")
                    if not command:
                        raise ValueError("Missing required field 'command' for stdio server")
                    server_tools = await clients.connect_stdio(
                        command,
                        cfg.get("args", []),
                        server_id=server_id,
                        env=cfg.get("env"),
                        cwd=cfg.get("cwd"),
                        timeout=timeout,
                    )
                else:
                    raise ValueError(f"Unknown MCP server type: {transport}")

                statuses.append(
                    {
                        "id": server_id,
                        "type": transport,
                        "enabled": True,
                        "status": "connected",
                        "error": None,
                        "tool_count": len(server_tools),
                        "tools": [
                            {
                                "name": tool.name,
                                "original_name": tool.original_name,
                                "description": tool.description,
                            }
                            for tool in server_tools
                        ],
                    }
                )
            except TimeoutError:
                err_msg = f"Connection timed out after {int(timeout)}s"
                logger.error("MCP connect timed out for %s: %s", server_id, err_msg)
                statuses.append(
                    {
                        "id": server_id,
                        "type": transport,
                        "enabled": True,
                        "status": "error",
                        "error": err_msg,
                        "tool_count": 0,
                        "tools": [],
                    }
                )
            except Exception as e:
                logger.error("MCP connect failed for %s: %s", server_id, e)
                statuses.append(
                    {
                        "id": server_id,
                        "type": transport,
                        "enabled": True,
                        "status": "error",
                        "error": str(e),
                        "tool_count": 0,
                        "tools": [],
                    }
                )
    except asyncio.CancelledError:
        await clients.disconnect()
        raise

    _CLIENTS = clients
    _SERVER_STATUSES = statuses
    logger.info("Loaded %d MCP tools from %d servers", len(clients.tools), len(normalized_servers))
    return list(clients.tools)


async def reload_mcp_tools(
    servers_config: dict[str, Any] | str,
    enabled: bool | None = None,
    thread_id: str | None = None,
) -> list[BaseTool]:
    return await init_mcp_tools(
        servers_override=servers_config,
        enabled=enabled,
        thread_id=thread_id,
    )


async def close_mcp_tools() -> None:
    async with _CLIENTS_LOCK:
        await _close_mcp_tools()


async def _close_mcp_tools() -> None:
    global _CLIENTS, _SERVER_STATUSES
    if _CLIENTS is not None:
        await _CLIENTS.disconnect()
        _CLIENTS = None
    _SERVER_STATUSES = []
