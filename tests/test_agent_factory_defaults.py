import sys
from pathlib import Path

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain.agents.middleware.todo import (
    WRITE_TODOS_SYSTEM_PROMPT,
    WRITE_TODOS_TOOL_DESCRIPTION,
)

from agent.workflows import agent_factory
from common.config import Settings


def test_build_middlewares_include_retry_and_limit_by_default(monkeypatch):
    settings_with_defaults = Settings(_env_file=None)
    monkeypatch.setattr(agent_factory, "settings", settings_with_defaults)

    middlewares = agent_factory._build_middlewares()
    names = {type(middleware).__name__ for middleware in middlewares}

    assert "ProviderSafeToolSelectorMiddleware" in names
    assert "ToolRetryMiddleware" in names
    assert "ToolCallLimitMiddleware" in names
    assert "TodoListMiddleware" in names

    selector = next(
        middleware
        for middleware in middlewares
        if type(middleware).__name__ == "ProviderSafeToolSelectorMiddleware"
    )
    assert "write_todos" in selector.always_include


def test_build_middlewares_keep_todo_defaults_when_settings_blank(monkeypatch):
    settings_with_defaults = Settings(
        _env_file=None,
        enable_todo_middleware=True,
        todo_system_prompt="",
        todo_tool_description="",
    )
    monkeypatch.setattr(agent_factory, "settings", settings_with_defaults)

    middlewares = agent_factory._build_middlewares()
    todo_middleware = next(
        middleware
        for middleware in middlewares
        if type(middleware).__name__ == "TodoListMiddleware"
    )

    assert todo_middleware.system_prompt == WRITE_TODOS_SYSTEM_PROMPT
    assert todo_middleware.tool_description == WRITE_TODOS_TOOL_DESCRIPTION


def test_non_openai_selector_prefers_json_mode(monkeypatch):
    settings_with_defaults = Settings(
        _env_file=None,
        openai_base_url="https://api.deepseek.com/v1",
    )
    monkeypatch.setattr(agent_factory, "settings", settings_with_defaults)

    assert agent_factory._tool_selector_methods() == (
        "json_mode",
        "function_calling",
        "json_schema",
    )
