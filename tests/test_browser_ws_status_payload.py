import main


def test_browser_stream_ws_initial_status_includes_mode_and_thread_id(monkeypatch):
    # Ensure WS auth is not required for this unit test.
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_status"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        msg = ws.receive_json()

    assert msg["type"] == "status"
    assert msg["thread_id"] == thread_id
    assert msg["mode"] in {"e2b", "local"}

