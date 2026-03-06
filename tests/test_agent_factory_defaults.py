import sys
from pathlib import Path

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.workflows import agent_factory
from common.config import Settings


def test_build_middlewares_include_retry_and_limit_by_default(monkeypatch):
    settings_with_defaults = Settings(_env_file=None)
    monkeypatch.setattr(agent_factory, "settings", settings_with_defaults)

    middlewares = agent_factory._build_middlewares()
    names = {type(middleware).__name__ for middleware in middlewares}

    assert "ToolRetryMiddleware" in names
    assert "ToolCallLimitMiddleware" in names
    assert "TodoListMiddleware" not in names
