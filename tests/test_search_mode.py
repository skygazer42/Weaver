import sys
from pathlib import Path

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import SearchMode, _normalize_search_mode


def test_normalize_search_mode_agent_string():
    mode = _normalize_search_mode("agent")
    assert mode["mode"] == "agent"
    assert mode["use_agent"] is True
    assert mode["use_deep"] is False


def test_normalize_search_mode_deep_string():
    mode = _normalize_search_mode("deep")
    assert mode["mode"] == "deep"
    assert mode["use_agent"] is True
    assert mode["use_deep"] is True


def test_normalize_search_mode_object_flags():
    mode = _normalize_search_mode(
        SearchMode(useWebSearch=True, useAgent=False, useDeepSearch=False)
    )
    assert mode["mode"] == "web"
    assert mode["use_web"] is True


def test_normalize_search_mode_deep_requires_agent():
    mode = _normalize_search_mode({"useDeepSearch": True, "useAgent": False, "useWebSearch": False})
    assert mode["use_deep"] is False
    assert mode["use_agent"] is False
    assert mode["mode"] == "direct"
