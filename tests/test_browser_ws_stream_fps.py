import asyncio
import json
import time
from concurrent.futures import TimeoutError as FutureTimeout

import main


def _receive_json_with_timeout(ws, *, timeout_s: float = 1.5):
    fut = ws.portal.start_task_soon(ws._send_rx.receive)
    try:
        message = fut.result(timeout=timeout_s)
    except FutureTimeout:
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


class _DummyPage:
    def __init__(self):
        self.url = "about:blank"
        self.contents: list[str] = []

    def title(self):
        return "Dummy"

    def set_content(self, html):
        self.contents.append(str(html))

    def screenshot(self, **_kwargs):
        return b"fake_jpeg_bytes"


class _DummyBrowserSession:
    def __init__(self):
        self.page = _DummyPage()
        self.started = 0
        self.stopped = 0

    def get_page(self):
        return self.page

    def start_screencast(self, **_kwargs):
        self.started += 1
        return True

    def stop_screencast(self):
        self.stopped += 1


class _RepeatingFrameSandboxBrowserSessions:
    def __init__(self):
        self.session = _DummyBrowserSession()
        self.peek_calls = 0

    def get(self, _thread_id: str):
        return self.session

    async def run_async(self, thread_id: str, fn, *args, **kwargs):
        _ = thread_id
        return fn(*args, **kwargs)

    def peek_screencast_frame(self, _thread_id: str):
        self.peek_calls += 1
        return {
            "frame_id": 1,
            "data": "ZmFrZV9qcGVn",
            "timestamp": 123.456,
            "metadata": {"url": "about:blank"},
        }


class _SlowScreenshotSandboxBrowserSessions:
    def __init__(self):
        self.session = _DummyBrowserSession()
        self.capture_calls = 0

    def get(self, _thread_id: str):
        return self.session

    async def run_async(self, thread_id: str, fn, *args, **kwargs):
        _ = thread_id
        if getattr(fn, "__name__", "") == "_capture":
            self.capture_calls += 1
            await asyncio.sleep(0.15)
        return fn(*args, **kwargs)

    def peek_screencast_frame(self, _thread_id: str):
        return None


def test_browser_stream_ws_repeats_same_frame_at_requested_fps(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")
    monkeypatch.setitem(main.settings.__dict__, "e2b_api_key", "e2b_test_key")
    monkeypatch.setitem(main.settings.__dict__, "sandbox_template_browser", "sandbox_template_test_browser")

    dummy = _RepeatingFrameSandboxBrowserSessions()
    monkeypatch.setattr(main, "sandbox_browser_sessions", dummy)

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_stream_repeated_frame_fps"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        initial = _receive_json_with_timeout(ws, timeout_s=1.0)
        assert initial["type"] == "status"

        ws.send_json({"action": "start", "quality": 70, "max_fps": 10})
        started = _receive_json_with_timeout(ws, timeout_s=1.5)
        assert started["type"] == "status"
        assert started["message"] == "Screencast started"

        frames = []
        for _ in range(4):
            msg = _receive_json_with_timeout(ws, timeout_s=0.35)
            assert msg["type"] == "frame"
            frames.append(msg)

    assert len(frames) == 4
    assert all(frame.get("source") == "cdp" for frame in frames)
    assert dummy.session.started == 1


def test_browser_stream_ws_reuses_last_frame_while_waiting_for_cdp(monkeypatch):
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")
    monkeypatch.setitem(main.settings.__dict__, "e2b_api_key", "e2b_test_key")
    monkeypatch.setitem(main.settings.__dict__, "sandbox_template_browser", "sandbox_template_test_browser")

    dummy = _SlowScreenshotSandboxBrowserSessions()
    monkeypatch.setattr(main, "sandbox_browser_sessions", dummy)

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_stream_bootstrap_frame_fps"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        initial = _receive_json_with_timeout(ws, timeout_s=1.0)
        assert initial["type"] == "status"

        ws.send_json({"action": "start", "quality": 70, "max_fps": 10})
        started = _receive_json_with_timeout(ws, timeout_s=1.5)
        assert started["type"] == "status"
        assert started["message"] == "Screencast started"

        frames = []
        started_at = time.perf_counter()
        for _ in range(4):
            msg = _receive_json_with_timeout(ws, timeout_s=0.35)
            assert msg["type"] == "frame"
            frames.append(msg)
        elapsed = time.perf_counter() - started_at

    assert len(frames) == 4
    assert elapsed < 0.6
    assert dummy.capture_calls <= 2
