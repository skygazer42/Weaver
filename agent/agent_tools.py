from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from tools import tavily_search, execute_python_code
from tools.registry import get_registered_tools
from tools.browser_tools import build_browser_tools
from tools.sandbox_browser_tools import build_sandbox_browser_tools
from tools.sandbox_web_search_tool import build_sandbox_web_search_tools
from tools.crawl_tools import build_crawl_tools
from tools.task_list_tool import build_task_list_tools
from tools.computer_use_tool import build_computer_use_tools


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
    - sandbox_browser: Playwright-based browser tools
    - sandbox_web_search: visual web search using sandbox browser
    - crawl: crawl_url(s) helpers
    - python: execute_python_code
    - task_list: task management tools (create, update, view tasks)
    - computer_use: desktop automation (mouse, keyboard, screenshots)
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

    # Sandbox web search: visual search using sandbox browser
    if _enabled(profile, "sandbox_web_search", default=False):
        tools.extend(build_sandbox_web_search_tools(thread_id))

    if _enabled(profile, "python", default=False):
        tools.append(execute_python_code)

    # Task list tools for structured task management
    if _enabled(profile, "task_list", default=False):
        tools.extend(build_task_list_tools(thread_id))

    # Computer use tools for desktop automation
    if _enabled(profile, "computer_use", default=False):
        computer_tools = build_computer_use_tools(thread_id)
        if computer_tools:  # Only add if pyautogui is available
            tools.extend(computer_tools)

    if _enabled(profile, "mcp", default=True):
        tools.extend(get_registered_tools())

    # De-dup by tool name to avoid collisions
    deduped: Dict[str, BaseTool] = {}
    for t in tools:
        name = getattr(t, "name", None)
        if isinstance(name, str) and name:
            deduped.setdefault(name, t)
    return list(deduped.values())
