from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.routing import APIRoute
from pydantic import UUID4, BaseModel, Field

from common.config import settings
from workbench.analysis import AnalysisError, run_csv_analysis

logger = logging.getLogger(__name__)
MAX_CSV_SIZE = 5 * 1024 * 1024
RECOVERY_INTERVAL_S = 5.0
RUN_FIELDS = "id, file_id, model, prompt, status, step, error, created_at, updated_at"
AVAILABLE = "(status = 'queued' OR (status = 'running' AND lease_until < ?))"
_tasks: dict[str, asyncio.Task[None]] = {}
_recovery_task: asyncio.Task[None] | None = None


class WorkspaceRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        if self.name != "upload_csv":
            return handler

        async def bounded_upload(request: Request) -> Response:
            limit = MAX_CSV_SIZE + 16 * 1024
            size = request.headers.get("content-length", "")
            if size.isdecimal() and int(size) > limit:
                raise HTTPException(status_code=413, detail="CSV file exceeds 5 MiB.")
            received = 0

            async def receive():
                nonlocal received
                message = await request.receive()
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail="CSV file exceeds 5 MiB.")
                return message

            return await handler(Request(request.scope, receive))

        return bounded_upload


router = APIRouter(prefix="/api/workspaces", tags=["workspaces"], route_class=WorkspaceRoute)


class WorkspaceFile(BaseModel):
    id: str
    name: str
    size: int
    created_at: str


class WorkspaceRun(BaseModel):
    id: str
    file_id: str
    model: str
    prompt: str
    status: Literal["queued", "running", "completed", "failed"]
    step: Literal["queued", "sandbox", "report", "completed", "failed"]
    error: str | None
    created_at: str
    updated_at: str


class Workspace(BaseModel):
    id: str
    files: list[WorkspaceFile]
    runs: list[WorkspaceRun]


class RunRequest(BaseModel):
    file_id: UUID4
    model: str = Field(default="", max_length=200)
    prompt: str = Field(default="", max_length=2000)


def _db_path() -> Path:
    root = os.getenv("WEAVER_DATA_DIR") or Path(__file__).resolve().parents[1] / "data"
    return Path(root) / "workspaces.sqlite3"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@contextmanager
def _database(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, owner TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                name TEXT NOT NULL, size INTEGER NOT NULL, created_at TEXT NOT NULL, content BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                file_id TEXT NOT NULL REFERENCES files(id), model TEXT NOT NULL, prompt TEXT NOT NULL,
                status TEXT NOT NULL, step TEXT NOT NULL, error TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                lease_until REAL, attempt TEXT, report TEXT, chart TEXT
            );
        """)
        yield db


def _require_workspace(db: sqlite3.Connection, workspace_id: str, request: Request) -> None:
    owner = getattr(request.state, "principal_id", "anonymous")
    if (
        db.execute(
            "SELECT 1 FROM workspaces WHERE id = ? AND owner = ?", (workspace_id, owner)
        ).fetchone()
        is None
    ):
        raise HTTPException(status_code=404, detail="Workspace not found")


def _schedule(path: Path, run_id: str) -> None:
    if run_id in _tasks:
        return
    task = asyncio.create_task(_execute_run(path, run_id))
    _tasks[run_id] = task
    task.add_done_callback(lambda _: _tasks.pop(run_id, None))


def _resume_available_runs(path: Path) -> None:
    if path.is_file():
        with _database(path) as db:
            pending = db.execute(
                f"SELECT id FROM runs WHERE {AVAILABLE}", (time.time(),)
            ).fetchall()
        for run in pending:
            _schedule(path, run["id"])


async def _recover_workspace_runs(path: Path) -> None:
    while True:
        await asyncio.sleep(RECOVERY_INTERVAL_S)
        _resume_available_runs(path)


async def start_workspace_runs() -> None:
    global _recovery_task
    path = _db_path()
    _resume_available_runs(path)
    _recovery_task = asyncio.create_task(_recover_workspace_runs(path))


async def stop_workspace_runs() -> None:
    global _recovery_task
    tasks = list(_tasks.values())
    if _recovery_task is not None:
        tasks.append(_recovery_task)
        _recovery_task = None
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _execute_run(path: Path, run_id: str) -> None:
    attempt = uuid4().hex
    with _database(path) as db:
        now = time.time()
        claimed = db.execute(
            f"""UPDATE runs SET status = 'running', step = 'sandbox', updated_at = ?,
                attempt = ?, lease_until = ? WHERE id = ? AND {AVAILABLE}""",
            (_now(), attempt, now + 300, run_id, now),
        ).rowcount
        if not claimed:
            return
        job = db.execute(
            "SELECT runs.model, runs.prompt, files.content FROM runs JOIN files ON files.id = runs.file_id WHERE runs.id = ?",
            (run_id,),
        ).fetchone()

    async def report_started() -> None:
        with _database(path) as db:
            db.execute(
                "UPDATE runs SET step = 'report', updated_at = ? WHERE id = ? AND attempt = ?",
                (_now(), run_id, attempt),
            )

    try:
        report, chart = await run_csv_analysis(
            job["content"], job["model"], job["prompt"], report_started
        )
    except asyncio.CancelledError:
        with _database(path) as db:
            db.execute(
                "UPDATE runs SET status = 'queued', step = 'queued', updated_at = ? WHERE id = ? AND attempt = ?",
                (_now(), run_id, attempt),
            )
        raise
    except Exception as error:
        logger.warning("Workspace run %s failed (%s)", run_id, type(error).__name__)
        message = (
            str(error)
            if isinstance(error, AnalysisError)
            else "分析失败。请检查沙盒和模型配置后重试。"
        )
        with _database(path) as db:
            db.execute(
                "UPDATE runs SET status = 'failed', step = 'failed', error = ?, updated_at = ? WHERE id = ? AND attempt = ?",
                (message, _now(), run_id, attempt),
            )
    else:
        with _database(path) as db:
            db.execute(
                """UPDATE runs SET status = 'completed', step = 'completed', report = ?, chart = ?, updated_at = ?
                   WHERE id = ? AND attempt = ?""",
                (report, chart, _now(), run_id, attempt),
            )


@router.post("", response_model=Workspace, status_code=201)
def create_workspace(request: Request) -> Workspace:
    workspace_id = uuid4().hex
    with _database(_db_path()) as db:
        db.execute(
            "INSERT INTO workspaces (id, owner) VALUES (?, ?)",
            (workspace_id, getattr(request.state, "principal_id", "anonymous")),
        )
    return Workspace(id=workspace_id, files=[], runs=[])


@router.get("/{workspace_id}", response_model=Workspace)
async def get_workspace(workspace_id: UUID4, request: Request) -> Workspace:
    path = _db_path()
    with _database(path) as db:
        _require_workspace(db, workspace_id.hex, request)
        files = db.execute(
            "SELECT id, name, size, created_at FROM files WHERE workspace_id = ? ORDER BY created_at DESC, rowid DESC",
            (workspace_id.hex,),
        ).fetchall()
        runs = db.execute(
            f"SELECT {RUN_FIELDS} FROM runs WHERE workspace_id = ? ORDER BY created_at DESC, rowid DESC",
            (workspace_id.hex,),
        ).fetchall()
    return Workspace(
        id=workspace_id.hex,
        files=[WorkspaceFile(**dict(row)) for row in files],
        runs=[WorkspaceRun(**dict(row)) for row in runs],
    )


@router.post("/{workspace_id}/files", response_model=WorkspaceFile, status_code=201)
async def upload_csv(workspace_id: UUID4, request: Request, file: UploadFile) -> WorkspaceFile:
    path = _db_path()
    with _database(path) as db:
        _require_workspace(db, workspace_id.hex, request)
    name = Path((file.filename or "").replace("\\", "/")).name
    if not name.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Upload a CSV file.")
    if len(name) > 255:
        raise HTTPException(status_code=422, detail="CSV filename exceeds 255 characters.")
    contents = await file.read(MAX_CSV_SIZE + 1)
    if not contents.strip():
        raise HTTPException(status_code=422, detail="CSV file is empty.")
    if len(contents) > MAX_CSV_SIZE:
        raise HTTPException(status_code=413, detail="CSV file exceeds 5 MiB.")

    saved = WorkspaceFile(id=uuid4().hex, name=name, size=len(contents), created_at=_now())
    with _database(path) as db:
        db.execute(
            "INSERT INTO files (id, workspace_id, name, size, created_at, content) VALUES (?, ?, ?, ?, ?, ?)",
            (saved.id, workspace_id.hex, name, saved.size, saved.created_at, contents),
        )
    return saved


def _frame(part: dict) -> str:
    return f"data: {json.dumps(part, ensure_ascii=False)}\n\n"


async def _stream_run(path: Path, run: dict) -> AsyncIterator[str]:
    run_id = run["id"]
    yield _frame({"type": "start", "messageId": run_id})
    yield _frame({"type": "data-run", "id": run_id, "data": run})
    last_event = time.monotonic()
    while run["status"] not in {"completed", "failed"}:
        await asyncio.sleep(0.4)
        with _database(path) as db:
            updated = dict(
                db.execute(f"SELECT {RUN_FIELDS} FROM runs WHERE id = ?", (run_id,)).fetchone()
            )
        if updated != run:
            run = updated
            yield _frame({"type": "data-run", "id": run_id, "data": run})
            last_event = time.monotonic()
        elif time.monotonic() - last_event >= 15:
            yield ": heartbeat\n\n"
            last_event = time.monotonic()
    yield _frame(
        {"type": "finish", "finishReason": "error" if run["status"] == "failed" else "stop"}
    )
    yield "data: [DONE]\n\n"


@router.post(
    "/{workspace_id}/runs",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def create_run(
    workspace_id: UUID4, request: Request, payload: RunRequest
) -> StreamingResponse:
    path = _db_path()
    with _database(path) as db:
        _require_workspace(db, workspace_id.hex, request)
        if not db.execute(
            "SELECT 1 FROM files WHERE workspace_id = ? AND id = ?",
            (workspace_id.hex, payload.file_id.hex),
        ).fetchone():
            raise HTTPException(status_code=404, detail="CSV file not found")
        if settings.use_azure or not settings.openai_api_key.strip():
            raise HTTPException(
                status_code=503,
                detail="Configure SiliconFlow or an OpenAI-compatible model provider before running analysis.",
            )
        stamp = _now()
        run = WorkspaceRun(
            id=uuid4().hex,
            file_id=payload.file_id.hex,
            model=payload.model.strip() or settings.primary_model,
            prompt=payload.prompt.strip(),
            status="queued",
            step="queued",
            error=None,
            created_at=stamp,
            updated_at=stamp,
        ).model_dump()
        db.execute(
            f"INSERT INTO runs (workspace_id, {RUN_FIELDS}) VALUES (:workspace_id, :id, :file_id, :model, :prompt, :status, :step, :error, :created_at, :updated_at)",
            {"workspace_id": workspace_id.hex, **run},
        )
    _schedule(path, run["id"])
    return StreamingResponse(
        _stream_run(path, run),
        media_type="text/event-stream",
        headers={
            "x-vercel-ai-ui-message-stream": "v1",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{workspace_id}/runs/{run_id}/artifacts/{name}", response_class=Response)
def get_artifact(
    workspace_id: UUID4,
    run_id: UUID4,
    name: Literal["report.md", "chart.svg"],
    request: Request,
) -> Response:
    with _database(_db_path()) as db:
        _require_workspace(db, workspace_id.hex, request)
        row = db.execute(
            "SELECT report, chart FROM runs WHERE id = ? AND workspace_id = ? AND status = 'completed'",
            (run_id.hex, workspace_id.hex),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if name == "report.md":
        return Response(
            row["report"],
            media_type="text/markdown",
            headers={"Cache-Control": "private, no-store"},
        )
    return Response(
        row["chart"], media_type="image/svg+xml", headers={"Cache-Control": "private, no-store"}
    )
