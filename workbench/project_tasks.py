"""Project workflows and their deliverables on the durable Agent runtime."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import UUID4, BaseModel, Field, StringConstraints
from starlette.concurrency import run_in_threadpool

from common.config import settings
from common.durable_streams import DurableStreams
from common.research_streams import run_status_line
from common.run_journal import RunRecord
from workbench.api import _request_owner, load_project_context
from workbench.project_workflows import ProjectWorkflowError, run_project_workflow

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["workspaces"])
Workflow = Literal["requirements-spec", "release-brief"]
TaskId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
TaskStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    "insufficient_evidence",
    "awaiting_approval",
]


class ProjectTaskRequest(BaseModel):
    workflow: Workflow
    request_id: TaskId
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    model: str | None = Field(default=None, max_length=200)
    file_ids: list[UUID4] | None = Field(default=None, max_length=6)
    repository: str | None = Field(default=None, max_length=140)
    release_tag: str | None = Field(default=None, max_length=200)
    artifact_id: UUID4 | None = None


class ProjectTask(BaseModel):
    id: str
    workflow: Workflow
    prompt: str
    status: TaskStatus
    artifact_id: str | None
    repository: str | None
    release_tag: str | None
    file_ids: list[str]
    created_at: datetime
    error: str | None = None


class ProjectSource(BaseModel):
    id: str
    title: str
    kind: str
    snippet: str
    url: str | None = None
    repository: str | None = None
    release_tag: str | None = None


class ProjectDeliverable(BaseModel):
    id: str
    task_id: str
    title: str
    content: str
    sources: list[ProjectSource]
    workflow: Workflow
    based_on: str | None
    created_at: datetime


def _run_id(workspace_id: str, task_id: str) -> str:
    return f"workspace:{workspace_id}:{task_id}"


def _artifact_id(thread_id: str) -> str:
    return thread_id.removeprefix("thread_")


def _legacy_event(kind: str, data: dict) -> str:
    return f"0:{json.dumps({'type': kind, 'data': data}, ensure_ascii=False)}\n"


def _task_view(task: dict, thread_id: str, status: str, *, error: str | None = None) -> ProjectTask:
    return ProjectTask(
        id=task["request_id"],
        workflow=task["workflow"],
        prompt=task["prompt"],
        status=status,
        artifact_id=_artifact_id(thread_id) if status == "completed" else None,
        repository=task["repository"],
        release_tag=task["release_tag"],
        file_ids=task["file_ids"],
        created_at=task["created_at"],
        error=error,
    )


async def _streams(workspace_id: UUID4, request: Request) -> DurableStreams:
    await run_in_threadpool(load_project_context, workspace_id.hex, _request_owner(request), [])
    streams = getattr(request.app.state, "project_streams", None)
    if streams is None:
        raise HTTPException(503, "Configure DATABASE_URL to run and save project workflows.")
    return streams


async def project_chat_context(workspace_id: UUID4, request: Request) -> dict:
    owner = _request_owner(request)
    context = await run_in_threadpool(load_project_context, workspace_id.hex, owner)
    for file in context["files"]:
        file["url"] = f"/api/workspaces/{workspace_id.hex}/files/{file['id']}"
    streams = getattr(request.app.state, "project_streams", None)
    deliverables = (
        await streams.journal.project_deliverables(owner, workspace_id.hex, limit=2)
        if streams is not None
        else []
    )
    context["deliverables"] = [
        {
            "title": item["title"],
            "excerpt": item["content"][:4000],
            "url": f"/api/workspaces/{workspace_id.hex}/deliverables/{item['id']}/download",
        }
        for item in deliverables
    ]
    return context


async def _deliverable(
    streams: DurableStreams, owner: str, workspace_id: str, artifact_id: str
) -> dict:
    found = await streams.journal.project_deliverables(
        owner, workspace_id, thread_id=f"thread_{artifact_id}"
    )
    if not found:
        raise HTTPException(404, "Deliverable not found")
    return found[0]


async def project_task_source(record: RunRecord) -> AsyncIterator[str]:
    saved = record.payload
    task = saved["project_task"]
    try:
        async for kind, data in run_project_workflow(
            task["workflow"],
            prompt=task["prompt"],
            model=task["model"],
            context=saved["context"],
            repository=task["repository"],
            release_tag=task["release_tag"],
            prior=saved["prior"],
        ):
            if kind == "deliverable":
                artifact = ProjectDeliverable(
                    id=_artifact_id(record.thread_id),
                    task_id=task["request_id"],
                    workflow=task["workflow"],
                    based_on=task["artifact_id"],
                    created_at=datetime.now(UTC),
                    **data,
                )
                yield _legacy_event("artifact", artifact.model_dump(mode="json"))
                return
            yield _legacy_event(kind, data)
        yield _legacy_event("error", {"message": "The workflow did not produce a deliverable."})
    except ProjectWorkflowError as error:
        yield _legacy_event("error", {"message": str(error)})


@router.post("/tasks", response_model=ProjectTask, status_code=202)
async def submit_project_task(workspace_id: UUID4, payload: ProjectTaskRequest, request: Request):
    streams = await _streams(workspace_id, request)
    owner = _request_owner(request)
    run_id = _run_id(workspace_id.hex, payload.request_id)
    existing = await streams.journal.get(owner, run_id)
    if existing is not None:
        streams.schedule(existing)
        return _task_view(existing.payload["project_task"], existing.thread_id, existing.status)
    if not settings.openai_api_key.strip():
        raise HTTPException(503, "Configure a model provider before running project workflows.")

    prior = None
    inherited_ids = None
    repository = (payload.repository or "").strip()
    release_tag = (payload.release_tag or "").strip()
    if payload.artifact_id is not None:
        prior = await _deliverable(streams, owner, workspace_id.hex, payload.artifact_id.hex)
        if prior["workflow"] != payload.workflow:
            raise HTTPException(422, "A revision must use the original workflow.")
        original = await streams.journal.get(owner, _run_id(workspace_id.hex, prior["task_id"]))
        inherited_ids = original.payload["project_task"]["file_ids"]
        if not repository:
            release = next(
                (source for source in prior["sources"] if source["kind"] == "github_release"), {}
            )
            repository = release.get("repository") or ""
            release_tag = release_tag or release.get("release_tag") or ""
    if payload.workflow == "release-brief" and not repository:
        raise HTTPException(422, "Enter a public GitHub repository as owner/repo.")

    file_ids = (
        [file_id.hex for file_id in payload.file_ids]
        if payload.file_ids is not None
        else inherited_ids
    )
    context = await run_in_threadpool(load_project_context, workspace_id.hex, owner, file_ids)
    for file in context["files"]:
        file["url"] = f"/api/workspaces/{workspace_id.hex}/files/{file['id']}"
    task = {
        "request_id": payload.request_id,
        "workflow": payload.workflow,
        "prompt": payload.prompt,
        "model": (payload.model or "").strip() or settings.primary_model,
        "repository": repository or None,
        "release_tag": release_tag or None,
        "file_ids": [file["id"] for file in context["files"]],
        "artifact_id": payload.artifact_id.hex if payload.artifact_id else None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    run = await streams.journal.submit(
        owner,
        run_id,
        f"thread_{uuid4().hex}",
        {
            "workspace_id": workspace_id.hex,
            "project_task": task,
            "context": context,
            "prior": prior,
        },
    )
    streams.schedule(run)
    return _task_view(run.payload["project_task"], run.thread_id, run.status)


@router.get("/tasks", response_model=list[ProjectTask])
async def list_project_tasks(workspace_id: UUID4, request: Request):
    streams = await _streams(workspace_id, request)
    rows = await streams.journal.project_tasks(_request_owner(request), workspace_id.hex)
    result = []
    for row in rows:
        raw = row["error_event"]
        event = json.loads(raw[2:]) if raw else {}
        error = event["data"].get("message") if event.get("type") == "error" else None
        result.append(_task_view(row["task"], row["thread_id"], row["status"], error=error))
    return result


@router.get("/tasks/{task_id}/events", response_class=StreamingResponse)
async def stream_project_task(
    workspace_id: UUID4,
    task_id: TaskId,
    request: Request,
    last_event_id: Annotated[int, Header(alias="Last-Event-ID", ge=0)] = 0,
):
    streams = await _streams(workspace_id, request)
    run = await streams.journal.get(_request_owner(request), _run_id(workspace_id.hex, task_id))
    if run is None:
        raise HTTPException(404, "Task not found")
    if last_event_id > run.event_seq:
        raise HTTPException(400, "Last-Event-ID is ahead of the task stream")
    return StreamingResponse(
        streams.subscribe(run, last_event_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/tasks/{task_id}", status_code=202, response_model=ProjectTask)
async def stop_project_task(workspace_id: UUID4, task_id: TaskId, request: Request):
    streams = await _streams(workspace_id, request)
    owner = _request_owner(request)
    run_id = _run_id(workspace_id.hex, task_id)
    if await streams.journal.get(owner, run_id) is None:
        raise HTTPException(404, "Task not found")
    await streams.journal.request_cancel(owner, run_id, final_line=run_status_line("cancelled"))
    run = await streams.journal.get(owner, run_id)
    return _task_view(run.payload["project_task"], run.thread_id, run.status)


@router.get("/deliverables", response_model=list[ProjectDeliverable])
async def list_project_deliverables(workspace_id: UUID4, request: Request):
    streams = await _streams(workspace_id, request)
    return await streams.journal.project_deliverables(_request_owner(request), workspace_id.hex)


@router.get("/deliverables/{artifact_id}/download", response_class=Response)
async def download_project_deliverable(workspace_id: UUID4, artifact_id: UUID4, request: Request):
    streams = await _streams(workspace_id, request)
    artifact = await _deliverable(
        streams, _request_owner(request), workspace_id.hex, artifact_id.hex
    )
    return Response(
        artifact["content"],
        media_type="text/markdown",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="{artifact["workflow"]}-{artifact_id.hex}.md"',
            "X-Content-Type-Options": "nosniff",
        },
    )
