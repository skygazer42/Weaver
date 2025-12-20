from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from tools import tavily_search, execute_python_code
from tools.registry import get_registered_tools
from tools.browser_tools import build_browser_tools
from tools.crawl_tools import build_crawl_tools
from tools.task_list_tool import build_task_list_tools
from tools.computer_use_tool import build_computer_use_tools

# Sandbox tools (E2B)
from tools.sandbox import (
    build_sandbox_browser_tools,
    build_sandbox_web_search_tools,
    build_sandbox_files_tools,
    build_sandbox_shell_tools,
    build_sandbox_sheets_tools,
    build_sandbox_presentation_tools,
    build_presentation_outline_tools,
    build_presentation_v2_tools,
    build_sandbox_vision_tools,
    build_image_edit_tools,
)


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
    - sandbox_files: file operations in E2B sandbox (create, read, update, delete)
    - sandbox_shell: shell command execution in E2B sandbox
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

    # Sandbox files: file operations in E2B sandbox
    if _enabled(profile, "sandbox_files", default=False):
        tools.extend(build_sandbox_files_tools(thread_id))

    # Sandbox shell: command execution in E2B sandbox
    if _enabled(profile, "sandbox_shell", default=False):
        tools.extend(build_sandbox_shell_tools(thread_id))

    # Sandbox sheets: Excel/spreadsheet generation in E2B sandbox
    if _enabled(profile, "sandbox_sheets", default=False):
        tools.extend(build_sandbox_sheets_tools(thread_id))

    # Sandbox presentation: PowerPoint generation in E2B sandbox
    if _enabled(profile, "sandbox_presentation", default=False):
        tools.extend(build_sandbox_presentation_tools(thread_id))

    # Sandbox vision: Image analysis and OCR in E2B sandbox
    if _enabled(profile, "sandbox_vision", default=False):
        tools.extend(build_sandbox_vision_tools(thread_id))

    # Sandbox image edit: Advanced image editing in E2B sandbox
    if _enabled(profile, "sandbox_image_edit", default=False):
        tools.extend(build_image_edit_tools(thread_id))

    # Presentation outline: LLM-based PPT outline generation
    if _enabled(profile, "presentation_outline", default=False):
        tools.extend(build_presentation_outline_tools(thread_id))

    # Presentation v2: Enhanced PPT features (themes, transitions)
    if _enabled(profile, "presentation_v2", default=False):
        tools.extend(build_presentation_v2_tools(thread_id))

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
