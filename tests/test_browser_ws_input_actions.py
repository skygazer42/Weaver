import json
from concurrent.futures import TimeoutError as FutureTimeout

import main


def _receive_json_with_timeout(ws, *, timeout_s: float = 1.5):
    """
    Starlette's WebSocketTestSession has no built-in timeout.

    Use the underlying anyio portal future so a missing server response fails
    fast instead of hanging the test suite.
    """
    fut = ws.portal.start_task_soon(ws._send_rx.receive)
    try:
        message = fut.result(timeout=timeout_s)
    except FutureTimeout:
        # Best-effort: close to unblock the pending receive task.
        try:
            ws.close()
        except Exception:
            pass
        try:
            fut.result(timeout=2.0)
        except Exception:
            pass
        raise AssertionError("Timed out waiting for WebSocket message")

    ws._raise_on_close(message)
    return json.loads(message["text"])


class _DummyMouse:
    def __init__(self):
        self.calls: list[tuple] = []

    def click(self, x, y, *, button="left", click_count=1):
        self.calls.append(("click", int(x), int(y), button, int(click_count)))

    def move(self, x, y):
        self.calls.append(("move", int(x), int(y)))

    def down(self, *, button="left"):
        self.calls.append(("down", str(button)))

    def up(self, *, button="left"):
        self.calls.append(("up", str(button)))

    def wheel(self, dx, dy):
        self.calls.append(("wheel", int(dx), int(dy)))


class _DummyKeyboard:
    def __init__(self):
        self.calls: list[tuple] = []

    def press(self, key):
        self.calls.append(("press", str(key)))

    def type(self, text):
        self.calls.append(("type", str(text)))


class _DummyPage:
    def __init__(self):
        self.mouse = _DummyMouse()
        self.keyboard = _DummyKeyboard()
        self.url = "about:blank"

        # Match Playwright's shape (`page.viewport_size` is a dict or None).
        self.viewport_size = {"width": 1000, "height": 500}

    def title(self):
        return "Dummy"

    def evaluate(self, _expr):
        return {"w": 1000, "h": 500}

    def goto(self, url, **_kwargs):
        self.url = str(url)


class _DummyBrowserSession:
    def __init__(self):
        self.page = _DummyPage()

    def get_page(self):
        return self.page


class _DummySandboxBrowserSessions:
    def __init__(self):
        self.session = _DummyBrowserSession()

    def get(self, _thread_id: str):
        return self.session

    async def run_async(self, thread_id: str, fn, *args, **kwargs):
        _ = thread_id
        return fn(*args, **kwargs)


def test_browser_stream_ws_mouse_click_sends_ack_and_executes_page_click(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")

    dummy = _DummySandboxBrowserSessions()
    monkeypatch.setattr(main, "sandbox_browser_sessions", dummy)

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_input_click"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        initial = _receive_json_with_timeout(ws)
        assert initial["type"] == "status"

        ws.send_json(
            {
                "action": "mouse",
                "type": "click",
                "x": 0.5,
                "y": 0.5,
                "button": "left",
                "clicks": 1,
                "id": "c1",
            }
        )

        ack = _receive_json_with_timeout(ws)

    assert ack["type"] == "ack"
    assert ack["id"] == "c1"
    assert ack["ok"] is True

    # Normalized 0.5 maps to the middle of (1000x500) viewport.
    assert ("click", 500, 250, "left", 1) in dummy.session.page.mouse.calls


def test_browser_stream_ws_mouse_move_sends_ack_and_executes_page_move(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")

    dummy = _DummySandboxBrowserSessions()
    monkeypatch.setattr(main, "sandbox_browser_sessions", dummy)

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_input_mouse_move"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        initial = _receive_json_with_timeout(ws)
        assert initial["type"] == "status"

        ws.send_json(
            {
                "action": "mouse",
                "type": "move",
                "x": 0.1,
                "y": 0.2,
                "id": "m1",
            }
        )

        ack = _receive_json_with_timeout(ws)

    assert ack["type"] == "ack"
    assert ack["id"] == "m1"
    assert ack["ok"] is True
    assert ("move", 100, 100) in dummy.session.page.mouse.calls


def test_browser_stream_ws_mouse_down_up_send_ack_and_execute_page_calls(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")

    dummy = _DummySandboxBrowserSessions()
    monkeypatch.setattr(main, "sandbox_browser_sessions", dummy)

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_input_mouse_down_up"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        initial = _receive_json_with_timeout(ws)
        assert initial["type"] == "status"

        ws.send_json(
            {
                "action": "mouse",
                "type": "down",
                "button": "left",
                "id": "d1",
            }
        )
        ack_down = _receive_json_with_timeout(ws)

        ws.send_json(
            {
                "action": "mouse",
                "type": "up",
                "button": "left",
                "id": "u1",
            }
        )
        ack_up = _receive_json_with_timeout(ws)

    assert ack_down["type"] == "ack"
    assert ack_down["id"] == "d1"
    assert ack_down["ok"] is True
    assert ("down", "left") in dummy.session.page.mouse.calls

    assert ack_up["type"] == "ack"
    assert ack_up["id"] == "u1"
    assert ack_up["ok"] is True
    assert ("up", "left") in dummy.session.page.mouse.calls


def test_browser_stream_ws_mouse_click_uses_viewport_fallback_when_missing(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")

    dummy = _DummySandboxBrowserSessions()
    dummy.session.page.viewport_size = None
    monkeypatch.setattr(main, "sandbox_browser_sessions", dummy)

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_input_click_fallback"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        initial = _receive_json_with_timeout(ws)
        assert initial["type"] == "status"

        ws.send_json(
            {
                "action": "mouse",
                "type": "click",
                "x": 0.5,
                "y": 0.5,
                "button": "left",
                "clicks": 1,
                "id": "c2",
            }
        )

        ack = _receive_json_with_timeout(ws)

    assert ack["type"] == "ack"
    assert ack["id"] == "c2"
    assert ack["ok"] is True
    assert ("click", 500, 250, "left", 1) in dummy.session.page.mouse.calls


def test_browser_stream_ws_scroll_sends_ack_and_executes_page_wheel(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")

    dummy = _DummySandboxBrowserSessions()
    monkeypatch.setattr(main, "sandbox_browser_sessions", dummy)

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_input_scroll"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        initial = _receive_json_with_timeout(ws)
        assert initial["type"] == "status"

        ws.send_json(
            {
                "action": "scroll",
                "dx": 0,
                "dy": 240,
                "id": "s1",
            }
        )

        ack = _receive_json_with_timeout(ws)

    assert ack["type"] == "ack"
    assert ack["id"] == "s1"
    assert ack["ok"] is True
    assert ("wheel", 0, 240) in dummy.session.page.mouse.calls


def test_browser_stream_ws_keyboard_press_sends_ack_and_executes_page_press(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")

    dummy = _DummySandboxBrowserSessions()
    monkeypatch.setattr(main, "sandbox_browser_sessions", dummy)

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_input_keyboard_press"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        initial = _receive_json_with_timeout(ws)
        assert initial["type"] == "status"

        ws.send_json(
            {
                "action": "keyboard",
                "type": "press",
                "key": "Enter",
                "id": "k1",
            }
        )

        ack = _receive_json_with_timeout(ws)

    assert ack["type"] == "ack"
    assert ack["id"] == "k1"
    assert ack["ok"] is True
    assert ("press", "Enter") in dummy.session.page.keyboard.calls


def test_browser_stream_ws_keyboard_type_sends_ack_and_executes_page_type(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")

    dummy = _DummySandboxBrowserSessions()
    monkeypatch.setattr(main, "sandbox_browser_sessions", dummy)

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_input_keyboard_type"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        initial = _receive_json_with_timeout(ws)
        assert initial["type"] == "status"

        ws.send_json(
            {
                "action": "keyboard",
                "type": "type",
                "text": "hello",
                "id": "k2",
            }
        )

        ack = _receive_json_with_timeout(ws)

    assert ack["type"] == "ack"
    assert ack["id"] == "k2"
    assert ack["ok"] is True
    assert ("type", "hello") in dummy.session.page.keyboard.calls


def test_browser_stream_ws_navigate_sends_ack_and_executes_page_goto(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")

    dummy = _DummySandboxBrowserSessions()
    monkeypatch.setattr(main, "sandbox_browser_sessions", dummy)

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_input_navigate"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        initial = _receive_json_with_timeout(ws)
        assert initial["type"] == "status"

        ws.send_json(
            {
                "action": "navigate",
                "url": "https://example.com",
                "id": "n1",
            }
        )

        ack = _receive_json_with_timeout(ws)

    assert ack["type"] == "ack"
    assert ack["id"] == "n1"
    assert ack["ok"] is True
    assert dummy.session.page.url == "https://example.com"


def test_browser_stream_ws_unknown_action_sends_ack_error(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")

    dummy = _DummySandboxBrowserSessions()
    monkeypatch.setattr(main, "sandbox_browser_sessions", dummy)

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_input_unknown_action"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        initial = _receive_json_with_timeout(ws)
        assert initial["type"] == "status"

        ws.send_json(
            {
                "action": "does_not_exist",
                "id": "u_1",
            }
        )

        ack = _receive_json_with_timeout(ws)

    assert ack["type"] == "ack"
    assert ack["id"] == "u_1"
    assert ack["ok"] is False
    assert ack["action"] == "does_not_exist"
    assert "unsupported" in (ack.get("error") or "").lower()
