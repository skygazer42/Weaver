"""Tests for report export (HTML, DOCX, PDF fallback, and POST /api/export/content)."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from main import app
from tools.export import export_report

SAMPLE_MARKDOWN = """# 电网级储能分析

## 核心结论

- 电池系统成本持续下降，调频与容量市场回报更稳定。
- 并网排队周期仍是项目落地的主要瓶颈。

| 指标 | 2024 | 2025 |
| --- | --- | --- |
| 装机规模 | 42 GW | 58 GW |
"""


def test_export_report_docx_generates_valid_docx_bytes():
    docx_bytes = export_report(
        SAMPLE_MARKDOWN,
        format="docx",
        title="电网级储能分析",
        thread_id="test-thread-1",
        sources=["https://www.eia.gov/electricity/storage/"],
    )
    assert isinstance(docx_bytes, bytes)
    assert docx_bytes.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
        assert "电网级储能分析" in xml
        assert "https://www.eia.gov/electricity/storage/" in xml


def test_export_report_pdf_generates_valid_pdf_bytes():
    pdf_bytes = export_report(
        SAMPLE_MARKDOWN,
        format="pdf",
        title="电网级储能分析",
        thread_id="test-thread-1",
        sources=["https://www.eia.gov/electricity/storage/"],
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_export_content_endpoint_supports_pdf_and_docx():
    client = TestClient(app)

    pdf_resp = client.post(
        "/api/export/content",
        json={
            "title": "Grid Storage Report",
            "content": SAMPLE_MARKDOWN,
            "format": "pdf",
            "thread_id": "thread-demo",
            "sources": ["https://www.iea.org/reports/batteries"],
        },
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"].startswith("application/pdf")
    assert pdf_resp.content.startswith(b"%PDF")

    docx_resp = client.post(
        "/api/export/content",
        json={
            "title": "Grid Storage Report",
            "content": SAMPLE_MARKDOWN,
            "format": "docx",
            "thread_id": "thread-demo",
        },
    )
    assert docx_resp.status_code == 200
    assert "wordprocessingml.document" in docx_resp.headers["content-type"]
    assert docx_resp.content.startswith(b"PK")
