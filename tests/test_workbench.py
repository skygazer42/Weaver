from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


def test_csv_skill_profiles_columns():
    script = (
        Path(__file__).resolve().parents[1] / "workbench" / "skills" / "csv-analysis" / "analyze.py"
    )
    result = subprocess.run(
        [sys.executable, str(script)],
        input=b'\xef\xbb\xbfcity,sales\r\n"New\nYork",0\r\nParis,12\r\nBerlin,\r\n',
        capture_output=True,
        check=True,
    )
    profile = json.loads(result.stdout)
    assert profile["rows"] == 3
    assert profile["columns"][1] == {
        "name": "sales",
        "filled": 2,
        "numeric": 2,
        "min": 0,
        "max": 12,
    }


def test_csv_skill_preserves_rows_after_unnamed_header():
    script = (
        Path(__file__).resolve().parents[1] / "workbench" / "skills" / "csv-analysis" / "analyze.py"
    )
    result = subprocess.run(
        [sys.executable, str(script)], input=b",\n1,2\n3,4\n", capture_output=True, check=True
    )
    profile = json.loads(result.stdout)
    assert profile["rows"] == 2
    assert [column["name"] for column in profile["columns"]] == ["Column 1", "Column 2"]


@pytest.mark.asyncio
async def test_expired_workspace_runs_resume_without_a_browser(tmp_path, monkeypatch):
    from workbench import api

    monkeypatch.setenv("WEAVER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(api, "RECOVERY_INTERVAL_S", 0.03, raising=False)
    with api._database(api._db_path()) as db:
        db.execute("INSERT INTO workspaces VALUES ('workspace', 'owner')")
        db.execute("INSERT INTO files VALUES ('file', 'workspace', 'sales.csv', 4, 'now', 'a,b')")
        db.execute(
            """INSERT INTO runs (id, workspace_id, file_id, model, prompt, status, step, created_at,
                updated_at, lease_until) VALUES ('run', 'workspace', 'file', 'model', '', 'running',
                'report', 'now', 'now', ?)""",
            (time.time() + 0.2,),
        )
    completed = asyncio.Event()

    async def analyze(*_):
        completed.set()
        return "report", "chart"

    monkeypatch.setattr(api, "run_csv_analysis", analyze)
    await api.start_workspace_runs()
    try:
        await asyncio.wait_for(completed.wait(), timeout=2)
        with api._database(api._db_path()) as db:
            assert db.execute("SELECT status FROM runs").fetchone()[0] == "completed"
    finally:
        await api.stop_workspace_runs()


def test_workbench_persists_inputs_runs_and_artifacts(tmp_path, monkeypatch):
    from workbench import api

    monkeypatch.setenv("WEAVER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(api.settings, "openai_api_key", "test-key")

    async def analyze(contents, model, prompt, on_report):
        assert contents == b"category,value\na,1\nb,3\n"
        assert model == "provider/model"
        await on_report()
        return f"# Report\n\n{prompt}", '<svg xmlns="http://www.w3.org/2000/svg" />'

    monkeypatch.setattr(api, "run_csv_analysis", analyze)

    def create_app() -> FastAPI:
        app = FastAPI()

        @app.middleware("http")
        async def identify(request: Request, call_next):
            request.state.principal_id = request.headers.get("X-Test-User", "alice")
            return await call_next(request)

        app.include_router(api.router)
        return app

    with TestClient(create_app()) as client:
        created = client.post("/api/workspaces")
        assert created.status_code == 201
        workspace = f"/api/workspaces/{created.json()['id']}"
        assert client.get(workspace, headers={"X-Test-User": "bob"}).status_code == 404
        assert (
            client.post(f"{workspace}/files", files={"file": ("notes.txt", b"hi")}).status_code
            == 415
        )
        oversized = client.post(
            f"{workspace}/files",
            content=b"x" * (api.MAX_CSV_SIZE + 65536),
            headers={"content-type": "multipart/form-data; boundary=wrong"},
        )
        assert oversized.status_code == 413
        file = client.post(
            f"{workspace}/files", files={"file": ("sales.csv", b"category,value\na,1\nb,3\n")}
        )
        assert file.status_code == 201
        file_id = file.json()["id"]
        run = client.post(
            f"{workspace}/runs",
            json={"file_id": file_id, "model": "provider/model", "prompt": "Check values"},
        )
        assert run.status_code == 200
        assert run.headers["x-vercel-ai-ui-message-stream"] == "v1"
        events = [
            json.loads(line[6:]) for line in run.text.splitlines() if line.startswith("data: {")
        ]
        run_id = events[1]["id"]
        assert events[1]["data"]["status"] == "queued"
        assert events[-2]["data"]["status"] == "completed"

    with TestClient(create_app()) as reopened:
        restored = reopened.get(workspace).json()
        assert [file["id"] for file in restored["files"]] == [file_id]
        assert restored["runs"][0]["id"] == run_id
        assert restored["runs"][0]["status"] == "completed"
        artifact = f"{workspace}/runs/{run_id}/artifacts/report.md"
        assert reopened.get(artifact).text == "# Report\n\nCheck values"
        assert reopened.get(artifact, headers={"X-Test-User": "bob"}).status_code == 404
        second = reopened.post(
            f"{workspace}/runs", json={"file_id": file_id, "model": "provider/model"}
        )
        assert second.status_code == 200
        assert len(reopened.get(workspace).json()["runs"]) == 2
