import json

import pytest

import main


class _DummyGraph:
    async def astream_events(self, *args, **kwargs):
        yield {
            "event": "on_graph_end",
            "name": "agent",
            "data": {
                "output": {
                    "is_complete": True,
                    "final_report": "ok",
                    "scraped_content": [
                        {
                            "results": [
                                {"title": "A", "url": "https://example.com/?utm_source=x"},
                            ]
                        }
                    ],
                }
            },
        }


async def _noop_async(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_stream_emits_sources_before_completion(monkeypatch):
    monkeypatch.setattr(main, "research_graph", _DummyGraph())
    monkeypatch.setattr(main, "add_memory_entry", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "store_interaction", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "fetch_memories", lambda *args, **kwargs: [])
    monkeypatch.setattr(main, "remove_emitter", _noop_async)
    monkeypatch.setattr(main.browser_sessions, "reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.sandbox_browser_sessions, "reset", lambda *args, **kwargs: None)

    chunks: list[str] = []
    async for chunk in main.stream_agent_events("hi", thread_id="thread_test"):
        chunks.append(chunk)

    payloads = []
    for chunk in chunks:
        if not chunk.startswith("0:"):
            continue
        payloads.append(json.loads(chunk[2:]))

    types = [p.get("type") for p in payloads]
    assert "sources" in types
    assert "completion" in types
    assert types.index("sources") < types.index("completion")

    sources_payload = payloads[types.index("sources")]
    items = sources_payload.get("data", {}).get("items", [])
    assert items and items[0]["url"] == "https://example.com/"

