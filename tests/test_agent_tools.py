import sys
from pathlib import Path

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.agent_tools import build_agent_tools


def _names(tools):
    return sorted([getattr(t, "name", "") for t in tools if getattr(t, "name", "")])


def test_agent_tools_lightweight_browser_selected_by_default():
    cfg = {"configurable": {"thread_id": "t1", "agent_profile": {"enabled_tools": {"browser": True}}}}
    names = _names(build_agent_tools(cfg))
    assert "browser_navigate" in names
    assert "sb_browser_navigate" not in names


def test_agent_tools_sandbox_browser_selected_when_enabled():
    cfg = {"configurable": {"thread_id": "t2", "agent_profile": {"enabled_tools": {"sandbox_browser": True}}}}
    names = _names(build_agent_tools(cfg))
    assert "sb_browser_navigate" in names
    assert "browser_navigate" not in names

