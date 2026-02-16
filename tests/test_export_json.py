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
    assert isinstance(data.get("quality"), dict)

