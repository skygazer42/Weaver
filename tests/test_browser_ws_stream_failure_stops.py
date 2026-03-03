import json
from concurrent.futures import TimeoutError as FutureTimeout

import main


def _receive_json_with_timeout(ws, *, timeout_s: float = 2.5):
    """
    Starlette's WebSocketTestSession has no built-in timeout.

    Mirror the helper in `tests/test_browser_ws_input_actions.py` so failures
    don't hang the test suite.
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


class _FailingSandboxBrowserSessions:
    async def run_async(self, thread_id: str, fn, *args, **kwargs):
        _ = thread_id, fn, args, kwargs
        raise RuntimeError("dummy capture failure")


def test_browser_stream_ws_emits_stopped_status_after_consecutive_capture_failures(monkeypatch):
    # Ensure WS auth is not required for this unit test.
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")

    monkeypatch.setattr(main, "sandbox_browser_sessions", _FailingSandboxBrowserSessions())

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_stream_failures"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        initial = _receive_json_with_timeout(ws, timeout_s=1.5)
        assert initial["type"] == "status"

        ws.send_json({"action": "start", "quality": 50, "max_fps": 10})
        started = _receive_json_with_timeout(ws, timeout_s=2.5)
        assert started["type"] == "status"
        assert started["message"] == "Screencast started"

        saw_error = False
        stopped = None

        # The WS loop backs off exponentially: 0.25 + 0.5 + 1 + 2 + 2 ~= 5.75s.
        for _ in range(32):
            msg = _receive_json_with_timeout(ws, timeout_s=8.0)
            if msg.get("type") == "error":
                saw_error = True
            if msg.get("type") == "status" and msg.get("message") == "Screencast stopped":
                stopped = msg
                break

    assert saw_error is True
    assert stopped is not None
    assert stopped.get("reason") == "capture_failed"
    assert int(stopped.get("consecutive_failures") or 0) >= 5

