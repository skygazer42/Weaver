import json

import pytest

import main


def _parse_stream_events(chunks: list[str]) -> list[dict]:
    events: list[dict] = []
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("0:"):
                events.append(json.loads(line[2:]))
    return events


@pytest.mark.asyncio
async def test_deep_research_stream_emits_completion_after_human_review_without_sources(monkeypatch):
    report_text = "# Deep Research Report\n\nDetailed synthesis with findings [1]."
    sample_sources = [{"url": "https://example.com/report", "title": "Example Report"}]

    class _FakeGraph:
        async def astream_events(self, _graph_input, config=None, **_kwargs):
            yield {"event": "on_chain_start", "name": "deepsearch", "data": {}}
            # deepsearch finishes with sources + final_report, but is_complete=False
            yield {
                "event": "on_chain_end",
                "name": "deepsearch",
                "data": {
                    "output": {
                        "sources": sample_sources,
                        "final_report": report_text,
                        "is_complete": False,
                    }
                },
            }
            # human_review finishes with is_complete=True + final_report, without sources
            yield {"event": "on_chain_start", "name": "human_review", "data": {}}
            yield {
                "event": "on_chain_end",
                "name": "human_review",
                "data": {
                    "output": {
                        "final_report": report_text,
                        "is_complete": True,
                    }
                },
            }
            # outer LangGraph ends with merged state containing both sources and final_report
            yield {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {
                    "output": {
                        "sources": sample_sources,
                        "final_report": report_text,
                        "is_complete": True,
                    }
                },
            }

    monkeypatch.setattr(main, "research_graph", _FakeGraph())
    monkeypatch.setattr(main, "store_interaction", lambda *_a, **_kw: None)
    monkeypatch.setattr(main, "_store_add", lambda *_a, **_kw: None)

    chunks = [
        chunk
        async for chunk in main.stream_agent_events(
            input_text="调研 2026 年 AI 智能体落地情况",
            thread_id="thread_deep_completion_ok",
            model="deepseek-chat",
            search_mode="deep",
        )
    ]

    events = _parse_stream_events(chunks)
    completions = [e for e in events if e.get("type") == "completion"]
    artifacts = [e for e in events if e.get("type") == "artifact"]
    sources_events = [e for e in events if e.get("type") == "sources"]
    insufficient = [e for e in events if e.get("type") == "insufficient_evidence"]

    assert len(sources_events) == 1
    assert sources_events[0]["data"]["items"][0]["url"] == "https://example.com/report"
    assert len(completions) == 1
    assert completions[0]["data"]["content"] == report_text
    assert len(artifacts) == 1
    assert artifacts[0]["data"]["content"] == report_text
    assert insufficient == []


@pytest.mark.asyncio
async def test_deep_research_stream_still_gates_when_no_sources_exist(monkeypatch):
    report_text = "Unsourced draft report"

    class _FakeEmptyGraph:
        async def astream_events(self, _graph_input, config=None, **_kwargs):
            yield {"event": "on_chain_start", "name": "deepsearch", "data": {}}
            yield {
                "event": "on_chain_end",
                "name": "deepsearch",
                "data": {"output": {"sources": [], "final_report": report_text, "is_complete": False}},
            }
            yield {
                "event": "on_chain_end",
                "name": "human_review",
                "data": {"output": {"final_report": report_text, "is_complete": True}},
            }

    monkeypatch.setattr(main, "research_graph", _FakeEmptyGraph())

    chunks = [
        chunk
        async for chunk in main.stream_agent_events(
            input_text="deep research topic",
            thread_id="thread_deep_completion_no_sources",
            model="deepseek-chat",
            search_mode="deep",
        )
    ]

    events = _parse_stream_events(chunks)
    assert [e for e in events if e.get("type") == "completion"] == []
    assert len([e for e in events if e.get("type") == "insufficient_evidence"]) == 1
