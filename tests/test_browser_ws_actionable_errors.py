import main


def test_browser_stream_ws_start_reports_actionable_missing_config(monkeypatch):
    # Disable auth for WS.
    monkeypatch.setitem(main.settings.__dict__, "internal_api_key", "")

    # Simulate missing sandbox configuration.
    monkeypatch.setitem(main.settings.__dict__, "e2b_api_key", "")
    monkeypatch.setitem(main.settings.__dict__, "sandbox_template_browser", "")

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    thread_id = "thread_test_ws_missing_cfg"

    with client.websocket_connect(f"/api/browser/{thread_id}/stream") as ws:
        _ = ws.receive_json()  # initial status
        ws.send_json({"action": "start"})
        msg = ws.receive_json()

    assert msg["type"] == "error"
    assert "missing" in msg
    assert "E2B_API_KEY" in msg["missing"]

