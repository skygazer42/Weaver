from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from tools import tavily_search, execute_python_code
from tools.registry import get_registered_tools
from tools.browser_tools import build_browser_tools
from tools.sandbox_browser_tools import build_sandbox_browser_tools
from tools.crawl_tools import build_crawl_tools


def _configurable(config: RunnableConfig) -> Dict[str, Any]:
    if isinstance(config, dict):
        cfg = config.get("configurable") or {}
        if isinstance(cfg, dict):
            return cfg
    return {}


def _enabled(profile: Dict[str, Any], key: str, default: bool = False) -> bool:
    enabled_tools = profile.get("enabled_tools") or {}
    if isinstance(enabled_tools, dict) and key in enabled_tools:
        return bool(enabled_tools.get(key))
    return default


def build_agent_tools(config: RunnableConfig) -> List[BaseTool]:
    """
    Build the toolset for "agent" mode based on `configurable.agent_profile.enabled_tools`.

    Tool keys:
    - web_search: tavily_search
    - browser: lightweight browser_* tools
    - crawl: crawl_url(s) helpers
    - python: execute_python_code
    - mcp: any loaded MCP tools
    """
    cfg = _configurable(config)
    profile = cfg.get("agent_profile") or {}
    if not isinstance(profile, dict):
        profile = {}

    thread_id = str(cfg.get("thread_id") or "default")

    tools: List[BaseTool] = []

    if _enabled(profile, "web_search", default=True):
        tools.append(tavily_search)

    if _enabled(profile, "crawl", default=True):
        tools.extend(build_crawl_tools())

    # Browser: prefer sandbox browser if explicitly enabled.
    if _enabled(profile, "sandbox_browser", default=False):
        tools.extend(build_sandbox_browser_tools(thread_id))
    elif _enabled(profile, "browser", default=False):
        tools.extend(build_browser_tools(thread_id))

    if _enabled(profile, "python", default=False):
        tools.append(execute_python_code)

    if _enabled(profile, "mcp", default=True):
        tools.extend(get_registered_tools())

    # De-dup by tool name to avoid collisions
    deduped: Dict[str, BaseTool] = {}
    for t in tools:
        name = getattr(t, "name", None)
        if isinstance(name, str) and name:
            deduped.setdefault(name, t)
    return list(deduped.values())
