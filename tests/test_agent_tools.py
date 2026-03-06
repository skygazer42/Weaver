import sys
from pathlib import Path

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.workflows.agent_tools import build_agent_tools
from common.config import settings


def _names(tools):
    return sorted([getattr(t, "name", "") for t in tools if getattr(t, "name", "")])


def test_agent_tools_lightweight_browser_selected_by_default():
    cfg = {
        "configurable": {"thread_id": "t1", "agent_profile": {"enabled_tools": {"browser": True}}}
    }
    names = _names(build_agent_tools(cfg))
    assert "browser_navigate" in names
    assert "sb_browser_navigate" not in names


def test_agent_tools_sandbox_browser_selected_when_enabled():
    # Sandbox tools require a configured E2B API key.
    original_key = settings.e2b_api_key
    settings.e2b_api_key = "e2b_test_key"
    try:
        cfg = {
            "configurable": {
                "thread_id": "t2",
                "agent_profile": {"enabled_tools": {"sandbox_browser": True}},
            }
        }
        names = _names(build_agent_tools(cfg))
    finally:
        settings.e2b_api_key = original_key
    assert "sb_browser_navigate" in names
    assert "browser_navigate" not in names


def test_agent_tools_web_dev_tools_when_enabled():
    # Sandbox tools require a configured E2B API key.
    original_key = settings.e2b_api_key
    settings.e2b_api_key = "e2b_test_key"
    try:
        cfg = {
            "configurable": {
                "thread_id": "t3",
                "agent_profile": {
                    "enabled_tools": {
                        "sandbox_web_dev": True,
                    }
                },
            }
        }
        names = _names(build_agent_tools(cfg))
    finally:
        settings.e2b_api_key = original_key
    assert "sandbox_scaffold_web_project" in names
    assert "sandbox_deploy_web_project" in names


def test_agent_tools_prefer_api_search_over_sandbox_search_when_web_search_enabled():
    original_key = settings.e2b_api_key
    original_search_engines = settings.search_engines
    original_mode = settings.sandbox_mode
    settings.e2b_api_key = "e2b_test_key"
    settings.search_engines = "tavily,serper"
    settings.sandbox_mode = "local"
    try:
        cfg = {
            "configurable": {
                "thread_id": "t4",
                "agent_profile": {
                    "enabled_tools": {
                        "web_search": True,
                        "sandbox_web_search": True,
                    }
                },
            }
        }
        names = _names(build_agent_tools(cfg))
    finally:
        settings.e2b_api_key = original_key
        settings.search_engines = original_search_engines
        settings.sandbox_mode = original_mode
    assert "fallback_search" in names
    assert "sandbox_web_search" not in names
    assert "sandbox_search_and_click" not in names
    assert "sandbox_extract_search_results" not in names


def test_agent_tools_include_sandbox_search_when_api_search_disabled():
    original_key = settings.e2b_api_key
    original_search_engines = settings.search_engines
    original_mode = settings.sandbox_mode
    settings.e2b_api_key = "e2b_test_key"
    settings.search_engines = "tavily,serper"
    settings.sandbox_mode = "local"
    try:
        cfg = {
            "configurable": {
                "thread_id": "t5",
                "agent_profile": {
                    "enabled_tools": {
                        "web_search": False,
                        "sandbox_web_search": True,
                    }
                },
            }
        }
        names = _names(build_agent_tools(cfg))
    finally:
        settings.e2b_api_key = original_key
        settings.search_engines = original_search_engines
        settings.sandbox_mode = original_mode
    assert "fallback_search" not in names
    assert "sandbox_web_search" in names


def test_agent_tools_include_task_list_tools_by_default():
    cfg = {
        "configurable": {
            "thread_id": "t_default_tasks",
            "agent_profile": {"enabled_tools": {}},
        }
    }
    names = _names(build_agent_tools(cfg))
    assert "create_tasks" in names
    assert "view_tasks" in names
    assert "update_task" in names
    assert "get_next_task" in names
    assert "plan_steps" in names
