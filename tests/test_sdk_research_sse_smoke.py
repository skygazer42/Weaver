from __future__ import annotations

import sys
from pathlib import Path

import httpx

SDK_PYTHON_ROOT = Path(__file__).resolve().parent.parent / "sdk" / "python"
sys.path.insert(0, str(SDK_PYTHON_ROOT))

from weaver_sdk.client import WeaverClient  # noqa: E402


def test_sdk_research_sse_parses_enveloped_events() -> None:
    sse_body = (
        b"id: 1\n"
        b"event: text\n"
        b'data: {"type":"text","data":{"content":"hi"}}\n'
        b"\n"
        b"id: 2\n"
        b"event: done\n"
        b'data: {"type":"done","data":{}}\n'
        b"\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/research/sse"
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/event-stream",
                "X-Thread-ID": "thread_test_123",
            },
            content=sse_body,
        )

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="http://test")
    client = WeaverClient(base_url="http://test", http=http)

    events = list(client.research_sse({"query": "hi"}))
    assert events[0]["type"] == "text"
    assert events[0]["data"]["content"] == "hi"
    assert events[1]["type"] == "done"
    assert client.last_thread_id == "thread_test_123"

