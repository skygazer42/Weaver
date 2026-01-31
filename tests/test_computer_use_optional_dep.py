import importlib
import importlib.util


def test_computer_use_tools_disabled_when_pyautogui_missing(monkeypatch):
    """computer_use tools should gracefully disable when pyautogui isn\x27t installed."""
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name, package=None):
        if name == "pyautogui":
            return None
        return real_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    import tools.automation.computer_use_tool as mod

    importlib.reload(mod)

    assert mod.PYAUTOGUI_AVAILABLE is False
    assert mod.build_computer_use_tools("thread-test") == []
