from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from workbench import api


@pytest.fixture
def workspace_client(tmp_path, monkeypatch):
    monkeypatch.setenv("WEAVER_DATA_DIR", str(tmp_path))
    app = FastAPI()

    @app.middleware("http")
    async def identify(request: Request, call_next):
        request.state.principal_id = request.headers.get("X-Test-User", "alice")
        return await call_next(request)

    app.include_router(api.router)
    with TestClient(app) as client:
        yield client


def create_workspace(client):
    response = client.post("/api/workspaces")
    assert response.status_code == 201
    return response.json()["id"]


def upload_file(client, workspace_id, name, contents):
    response = client.post(
        f"/api/workspaces/{workspace_id}/files", files={"file": (name, contents)}
    )
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def test_project_metadata_is_saved_per_owner(workspace_client):
    workspace_id = create_workspace(workspace_client)
    url = f"/api/workspaces/{workspace_id}"
    default = {"name": "Workspace", "instructions": "", "decisions": ""}
    assert workspace_client.get(url).json() == {
        "id": workspace_id,
        "files": [],
        "runs": [],
        **default,
    }

    metadata = {"name": "  Forecast  ", "instructions": "Cite sources.", "decisions": "Use Q2."}
    assert workspace_client.patch(url, json=metadata).status_code == 200
    assert workspace_client.patch(url, json={"decisions": ""}).status_code == 200
    assert workspace_client.patch(url, json={"name": " "}).status_code == 422
    assert workspace_client.patch(url, json={"name": None}).status_code == 422
    assert workspace_client.patch(url, json={"instructions": "x" * 100_000}).status_code == 422
    assert (
        workspace_client.patch(
            url, json={"name": "Private"}, headers={"X-Test-User": "bob"}
        ).status_code
        == 404
    )
    assert api.load_project_context(workspace_id, "alice", []) == {
        "name": "Forecast",
        "instructions": "Cite sources.",
        "decisions": "",
        "files": [],
    }


def test_project_file_download_keeps_bytes_and_checks_project_owner(workspace_client):
    workspace_id = create_workspace(workspace_client)
    other_workspace = create_workspace(workspace_client)
    contents = "Résumé ready\n".encode()
    file_id = upload_file(workspace_client, workspace_id, "résumé #1.txt", contents)
    suffix = f"/files/{file_id}"
    url = f"/api/workspaces/{workspace_id}{suffix}"
    response = workspace_client.get(url)
    assert response.content == contents
    assert (
        response.headers["content-disposition"]
        == "attachment; filename*=UTF-8''r%C3%A9sum%C3%A9%20%231.txt"
    )
    assert workspace_client.get(url, headers={"X-Test-User": "bob"}).status_code == 404
    assert workspace_client.get(f"/api/workspaces/{other_workspace}{suffix}").status_code == 404


@pytest.mark.parametrize(
    ("name", "contents", "status"),
    [
        ("asset.exe", b"text", 415),
        ("empty.md", b" \t", 422),
        ("binary.txt", b"\x00\x03\xffbinary", 422),
        ("fake.pdf", b"text", 422),
        ("fake.docx", b"text", 422),
    ],
)
def test_project_upload_checks_type_and_content(workspace_client, name, contents, status):
    workspace_id = create_workspace(workspace_client)
    response = workspace_client.post(
        f"/api/workspaces/{workspace_id}/files", files={"file": (name, contents)}
    )
    assert response.status_code == status


def test_project_upload_rejects_oversized_docx_archive(workspace_client):
    workspace_id = create_workspace(workspace_client)
    contents = BytesIO()
    with ZipFile(contents, "w", ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", "<Types />")
        package.writestr("word/document.xml", b" " * (26 * 1024 * 1024))
    response = workspace_client.post(
        f"/api/workspaces/{workspace_id}/files", files={"file": ("large.docx", contents.getvalue())}
    )
    assert response.status_code == 413


def test_project_context_extracts_text_with_file_and_page_labels(workspace_client):
    from docx import Document
    from fitz import open as pdf_open

    workspace_id = create_workspace(workspace_client)
    docx_file = BytesIO()
    document = Document()
    document.add_paragraph("Forecast is available.")
    document.save(docx_file)
    docx_id = upload_file(workspace_client, workspace_id, "outline.docx", docx_file.getvalue())
    with pdf_open() as pdf:
        pdf.new_page().insert_text((50, 50), "March results")
        pdf.new_page().insert_text((50, 50), "June results")
        pdf_id = upload_file(workspace_client, workspace_id, "results.PDF", pdf.tobytes())
    markdown_id = upload_file(workspace_client, workspace_id, "notes.md", b"# Notes\n\n- Budget")
    csv_id = upload_file(
        workspace_client, workspace_id, "sales.csv", "品类,金额\nA,42".encode("gb18030")
    )

    assert api.load_project_context(workspace_id, "alice")["files"] == [
        {"id": markdown_id, "name": "notes.md", "text": "# Notes\n\n- Budget"},
        {
            "id": pdf_id,
            "name": "results.PDF",
            "text": "[Page 1]\nMarch results\n\n[Page 2]\nJune results",
        },
        {"id": docx_id, "name": "outline.docx", "text": "Forecast is available."},
    ]
    assert api.load_project_context(workspace_id, "alice", [csv_id])["files"] == [
        {"id": csv_id, "name": "sales.csv", "text": "品类,金额\nA,42"},
    ]
    response = workspace_client.post(
        f"/api/workspaces/{workspace_id}/runs", json={"file_id": markdown_id}
    )
    assert response.status_code == 415


def test_project_context_checks_explicit_files_and_owner(workspace_client):
    workspace_id = create_workspace(workspace_client)
    other_workspace = create_workspace(workspace_client)
    local_id = upload_file(workspace_client, workspace_id, "notes.txt", b"local")
    other_id = upload_file(workspace_client, other_workspace, "notes.txt", b"other")

    with pytest.raises(HTTPException) as forbidden_file:
        api.load_project_context(workspace_id, "alice", [local_id, other_id])
    assert forbidden_file.value.status_code == 404
    with pytest.raises(HTTPException) as forbidden_workspace:
        api.load_project_context(workspace_id, "bob", [])
    assert forbidden_workspace.value.status_code == 404


def test_project_context_limits_excerpt_size_and_skips_unreadable_implicit_files(workspace_client):
    from fitz import open as pdf_open

    workspace_id = create_workspace(workspace_client)
    for index in range(8):
        upload_file(workspace_client, workspace_id, f"notes-{index}.txt", b"d" * 10_000)
    with pdf_open() as pdf:
        pdf.new_page()
        pdf_id = upload_file(workspace_client, workspace_id, "empty.pdf", pdf.tobytes())

    with pytest.raises(HTTPException) as unreadable:
        api.load_project_context(workspace_id, "alice", [pdf_id])
    assert unreadable.value.status_code == 422
    assert "empty.pdf" in unreadable.value.detail
    files = api.load_project_context(workspace_id, "alice")["files"]
    assert [file["name"] for file in files] == [f"notes-{index}.txt" for index in range(7, 1, -1)]
    assert sum(len(file["text"]) for file in files) <= 24_000
