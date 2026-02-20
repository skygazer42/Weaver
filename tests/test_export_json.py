from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.mark.asyncio
async def test_export_report_json_includes_evidence_payload(monkeypatch):
    state = {
        "final_report": "According to the report, revenue increased by 20% in 2024.",
        "scraped_content": [
            {
                "results": [
                    {
                        "title": "Annual Report",
                        "url": "https://example.com/?utm_source=test",
                        "summary": "The annual report shows revenue increased by 20% in 2024.",
                    }
                ]
            }
        ],
        "quality_summary": {"summary_count": 1, "source_count": 1},
    }

    checkpoint = SimpleNamespace(checkpoint={"channel_values": state})
    monkeypatch.setattr(
        main,
        "checkpointer",
        SimpleNamespace(get_tuple=lambda config: checkpoint),
    )

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/export/thread-1", params={"format": "json"})

    assert resp.status_code == 200
    assert "application/json" in (resp.headers.get("content-type") or "")
    data = resp.json()
    assert isinstance(data.get("report"), str)
    assert isinstance(data.get("sources"), list)
    assert isinstance(data.get("claims"), list)
    assert data.get("claims"), "expected claim verifier to produce at least one claim"
    claim = (data.get("claims") or [None])[0] or {}
    assert isinstance(claim.get("evidence_urls"), list)
    assert isinstance(claim.get("evidence_passages"), list)
    assert claim.get("evidence_passages"), "expected at least one passage-level evidence item"
    passage = (claim.get("evidence_passages") or [None])[0] or {}
    assert isinstance(passage.get("url"), str)
    assert "utm_source" not in passage.get("url")
    assert isinstance(data.get("quality"), dict)


@pytest.mark.asyncio
async def test_export_report_json_claim_verifier_prefers_passages_when_available(monkeypatch):
    state = {
        "final_report": "The company's revenue increased in 2024 according to the annual report.",
        "scraped_content": [],
        "deepsearch_artifacts": {
            "passages": [
                {
                    "url": "https://example.com/earnings?utm_source=test",
                    "text": "In 2024, the company's revenue increased by 5% year over year.",
                    "snippet_hash": "passage_123",
                    "quote": "In 2024, the company's revenue increased by 5% year over year.",
                    "heading_path": ["Results"],
                }
            ]
        },
    }

    checkpoint = SimpleNamespace(checkpoint={"channel_values": state})
    monkeypatch.setattr(
        main,
        "checkpointer",
        SimpleNamespace(get_tuple=lambda config: checkpoint),
    )

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/export/thread-2", params={"format": "json"})

    assert resp.status_code == 200
    data = resp.json() or {}
    assert isinstance(data.get("claims"), list)
    assert data.get("claims")
    claim = (data.get("claims") or [None])[0] or {}
    assert claim.get("status") in {"verified", "unsupported", "contradicted"}
    assert isinstance(claim.get("evidence_urls"), list)
    assert isinstance(claim.get("evidence_passages"), list)
    assert claim.get("evidence_passages"), "expected passage-level evidence to be attached"
    passage = (claim.get("evidence_passages") or [None])[0] or {}
    assert passage.get("snippet_hash") == "passage_123"
    assert passage.get("heading_path") == ["Results"]
    assert "utm_source" not in str(passage.get("url") or "")
