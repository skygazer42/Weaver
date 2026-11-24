from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.routing import APIRoute
from pydantic import UUID4, BaseModel, Field, StringConstraints

from common.config import settings
from workbench.analysis import AnalysisError, run_csv_analysis

logger = logging.getLogger(__name__)
MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_DOCX_EXPANDED_SIZE = 25 * 1024 * 1024
MAX_CONTEXT_CHARS = 24_000
MAX_CONTEXT_FILES = 6
FILE_MEDIA_TYPES = {
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
BINARY_CONTROL_BYTES = re.compile(rb"[\x00-\x08\x0b\x0e-\x1f\x7f]")
RECOVERY_INTERVAL_S = 5.0
RUN_FIELDS = "id, file_id, model, prompt, status, step, error, created_at, updated_at"
AVAILABLE = "(status = 'queued' OR (status = 'running' AND lease_until < ?))"
_tasks: dict[str, asyncio.Task[None]] = {}
_recovery_task: asyncio.Task[None] | None = None


class WorkspaceRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        if self.name != "upload_file":
            return handler

        async def bounded_upload(request: Request) -> Response:
            limit = MAX_FILE_SIZE + 16 * 1024
            size = request.headers.get("content-length", "")
            if size.isdecimal() and int(size) > limit:
                raise HTTPException(status_code=413, detail="File exceeds 5 MiB.")
            received = 0

            async def receive():
                nonlocal received
                message = await request.receive()
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail="File exceeds 5 MiB.")
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


class WorkspaceMetadata(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] = (
        "Workspace"
    )
    instructions: str = Field(default="", max_length=4000)
    decisions: str = Field(default="", max_length=4000)


class Workspace(WorkspaceMetadata):
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
            CREATE TABLE IF NOT EXISTS workspace_metadata (
                workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id),
                name TEXT NOT NULL, instructions TEXT NOT NULL, decisions TEXT NOT NULL
            );
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


def _request_owner(request: Request) -> str:
    return getattr(request.state, "principal_id", "anonymous")


def _require_workspace(db: sqlite3.Connection, workspace_id: str, owner: str) -> dict[str, str]:
    row = db.execute(
        """SELECT workspace_metadata.name, workspace_metadata.instructions, workspace_metadata.decisions
           FROM workspaces LEFT JOIN workspace_metadata ON workspace_metadata.workspace_id = workspaces.id
           WHERE workspaces.id = ? AND workspaces.owner = ?""",
        (workspace_id, owner),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return dict(row) if row["name"] is not None else WorkspaceMetadata().model_dump()


def _workspace_response(db: sqlite3.Connection, workspace_id: str, owner: str) -> Workspace:
    metadata = _require_workspace(db, workspace_id, owner)
    files = db.execute(
        "SELECT id, name, size, created_at FROM files WHERE workspace_id = ? ORDER BY created_at DESC, rowid DESC",
        (workspace_id,),
    )
    runs = db.execute(
        f"SELECT {RUN_FIELDS} FROM runs WHERE workspace_id = ? ORDER BY created_at DESC, rowid DESC",
        (workspace_id,),
    )
    return Workspace(
        id=workspace_id,
        **metadata,
        files=[WorkspaceFile(**dict(row)) for row in files],
        runs=[WorkspaceRun(**dict(row)) for row in runs],
    )


def _require_file(
    db: sqlite3.Connection, workspace_id: str, file_id: str, *, include_content: bool = False
) -> sqlite3.Row:
    fields = "id, name, content" if include_content else "id, name"
    row = db.execute(
        f"SELECT {fields} FROM files WHERE workspace_id = ? AND id = ?", (workspace_id, file_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="File not found")
    return row


def _decode_file_text(contents: bytes, suffix: str) -> str:
    if BINARY_CONTROL_BYTES.search(contents):
        raise ValueError("Binary bytes in a text file")
    try:
        return contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        if suffix != ".csv":
            raise
        return contents.decode("gb18030")


def _validate_upload(contents: bytes, suffix: str) -> None:
    if not contents.strip():
        raise HTTPException(status_code=422, detail="File is empty.")
    if suffix == ".pdf":
        if b"%PDF-" not in contents[:1024]:
            raise HTTPException(status_code=422, detail="Invalid PDF file.")
    elif suffix == ".docx":
        try:
            with ZipFile(BytesIO(contents)) as package:
                if {"[Content_Types].xml", "word/document.xml"} - set(package.namelist()):
                    raise BadZipFile("Missing DOCX document parts")
                if sum(entry.file_size for entry in package.infolist()) > MAX_DOCX_EXPANDED_SIZE:
                    raise HTTPException(
                        status_code=413, detail="DOCX file exceeds 25 MiB when unpacked."
                    )
        except BadZipFile as error:
            raise HTTPException(status_code=422, detail="Invalid DOCX file.") from error
    else:
        try:
            content = _decode_file_text(contents, suffix)
        except ValueError as error:
            raise HTTPException(
                status_code=422, detail="Invalid text file encoding or content."
            ) from error
        if not content.strip():
            raise HTTPException(status_code=422, detail="File is empty.")


def _project_file_text(contents: bytes, name: str, limit: int) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in {".csv", ".md", ".txt"}:
        return _decode_file_text(contents, suffix).strip()[:limit]
    if suffix in {".docx", ".pdf"}:
        from tools.rag.document_loader import DocumentLoader

        documents = DocumentLoader(chunk_size=limit).load_from_bytes(
            contents, name, max_chars=limit
        )
        return "\n\n".join(document.content for document in documents)
    raise ValueError("Unsupported file format")


def load_project_context(workspace_id: str, owner: str, file_ids: list[str] | None = None) -> dict:
    """Load bounded source excerpts for one workspace and owner."""
    with _database(_db_path()) as db:
        metadata = _require_workspace(db, workspace_id, owner)
        if file_ids is None:
            candidates = db.execute(
                """SELECT id, name FROM files WHERE workspace_id = ? AND lower(substr(name, -4)) != '.csv'
                   ORDER BY created_at DESC, rowid DESC""",
                (workspace_id,),
            ).fetchall()
            limit = MAX_CONTEXT_CHARS // MAX_CONTEXT_FILES
        else:
            candidates = [
                _require_file(db, workspace_id, file_id) for file_id in dict.fromkeys(file_ids)
            ]
            limit = min(6_000, MAX_CONTEXT_CHARS // max(1, len(candidates)))

        files = []
        for row in candidates:
            file = _require_file(db, workspace_id, row["id"], include_content=True)
            try:
                excerpt = _project_file_text(file["content"], file["name"], limit)
            except Exception as error:
                logger.warning(
                    "Workspace file %s extraction failed (%s)", file["id"], type(error).__name__
                )
                excerpt = ""
            if not excerpt.strip():
                if file_ids is not None:
                    raise HTTPException(
                        status_code=422, detail=f"Could not extract text from {file['name']}."
                    )
                continue
            files.append({"id": file["id"], "name": file["name"], "text": excerpt})
            if file_ids is None and len(files) == MAX_CONTEXT_FILES:
                break
    return {**metadata, "files": files}


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
            (workspace_id, _request_owner(request)),
        )
    return Workspace(id=workspace_id, files=[], runs=[])


@router.get("/{workspace_id}", response_model=Workspace)
def get_workspace(workspace_id: UUID4, request: Request) -> Workspace:
    with _database(_db_path()) as db:
        return _workspace_response(db, workspace_id.hex, _request_owner(request))


@router.patch("/{workspace_id}", response_model=Workspace)
def update_workspace(
    workspace_id: UUID4, request: Request, payload: WorkspaceMetadata
) -> Workspace:
    owner = _request_owner(request)
    changes = payload.model_dump(exclude_unset=True)
    with _database(_db_path()) as db:
        _require_workspace(db, workspace_id.hex, owner)
        if changes:
            db.execute(
                """INSERT INTO workspace_metadata (workspace_id, name, instructions, decisions)
                   VALUES (:id, COALESCE(:name, 'Workspace'), COALESCE(:instructions, ''), COALESCE(:decisions, ''))
                   ON CONFLICT(workspace_id) DO UPDATE SET
                       name = COALESCE(:name, name), instructions = COALESCE(:instructions, instructions),
                       decisions = COALESCE(:decisions, decisions)""",
                {
                    "id": workspace_id.hex,
                    "name": changes.get("name"),
                    "instructions": changes.get("instructions"),
                    "decisions": changes.get("decisions"),
                },
            )
        return _workspace_response(db, workspace_id.hex, owner)


@router.post("/{workspace_id}/files", response_model=WorkspaceFile, status_code=201)
async def upload_file(workspace_id: UUID4, request: Request, file: UploadFile) -> WorkspaceFile:
    path = _db_path()
    with _database(path) as db:
        _require_workspace(db, workspace_id.hex, _request_owner(request))
    name = Path((file.filename or "").replace("\\", "/")).name
    suffix = Path(name).suffix.lower()
    if suffix not in FILE_MEDIA_TYPES:
        raise HTTPException(status_code=415, detail="Upload a TXT, MD, PDF, DOCX, or CSV file.")
    if len(name) > 255 or not name.isprintable():
        raise HTTPException(
            status_code=422, detail="Use a printable filename of at most 255 characters."
        )
    contents = await file.read(MAX_FILE_SIZE + 1)
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 5 MiB.")
    await asyncio.to_thread(_validate_upload, contents, suffix)

    saved = WorkspaceFile(id=uuid4().hex, name=name, size=len(contents), created_at=_now())
    with _database(path) as db:
        db.execute(
            "INSERT INTO files (id, workspace_id, name, size, created_at, content) VALUES (?, ?, ?, ?, ?, ?)",
            (saved.id, workspace_id.hex, name, saved.size, saved.created_at, contents),
        )
    return saved


@router.get("/{workspace_id}/files/{file_id}", response_class=Response)
def download_file(workspace_id: UUID4, file_id: UUID4, request: Request) -> Response:
    with _database(_db_path()) as db:
        _require_workspace(db, workspace_id.hex, _request_owner(request))
        file = _require_file(db, workspace_id.hex, file_id.hex, include_content=True)
    filename = quote(file["name"], safe="")
    media_type = FILE_MEDIA_TYPES.get(Path(file["name"]).suffix.lower(), "application/octet-stream")
    return Response(
        file["content"],
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
        _require_workspace(db, workspace_id.hex, _request_owner(request))
        file = _require_file(db, workspace_id.hex, payload.file_id.hex)
        if not file["name"].lower().endswith(".csv"):
            raise HTTPException(status_code=415, detail="Select a CSV file for analysis.")
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
        _require_workspace(db, workspace_id.hex, _request_owner(request))
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
