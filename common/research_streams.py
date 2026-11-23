"""Keep a deep research run independent of its SSE subscribers."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import aclosing

from common.chat_stream_translate import translate_legacy_line_to_sse
from common.sse import format_sse_comment, format_sse_event

logger = logging.getLogger(__name__)
MAX_STREAMS = 32
MAX_REPLAY_BYTES = 8 * 1024 * 1024
REPLAY_SECONDS = 3600


def run_status_line(status: str) -> str:
    return "0:" + json.dumps({"type": "run_status", "data": {"status": status}}) + "\n"


def status_from_line(line: str, status: str) -> str:
    if not line.startswith("0:"):
        return status
    try:
        event = json.loads(line[2:]).get("type")
    except (ValueError, AttributeError):
        return status
    return {
        "interrupt": "awaiting_approval",
        "cancelled": "cancelled",
        "error": "failed",
        "insufficient_evidence": "insufficient_evidence",
    }.get(event, status)


class ResearchStreamCapacity(Exception):
    """All research stream slots are occupied by active runs."""


class ReplayTooLarge(Exception):
    """The run exceeded the size of its replay buffer."""


class ResearchStream:
    def __init__(self, thread_id: str, source: AsyncGenerator[str, None]):
        self.thread_id = thread_id
        self.frames: list[str] = []
        self.completed_at: float | None = None
        self._changed = asyncio.Event()
        self.status = "running"
        self.payload: dict = {}
        self._start(source)

    def _start(self, source: AsyncGenerator[str, None]) -> None:
        self.task = asyncio.create_task(self._collect(source))
        self.task.add_done_callback(self._finish)

    def resume(self, source: AsyncGenerator[str, None], *, expected_seq: int) -> bool:
        if self.status != "awaiting_approval" or self.completed_at is None or len(self.frames) != expected_seq:
            return False
        self.completed_at = None
        self.status = "running"
        self._append_line(run_status_line(self.status))
        self._start(source)
        return True

    def cancel_pending_approval(self) -> bool:
        if self.status != "awaiting_approval" or self.completed_at is None:
            return False
        self.status = "cancelled"
        self._append_line(run_status_line(self.status))
        return True

    def _append_line(self, line: str) -> None:
        frame = translate_legacy_line_to_sse(line, seq=len(self.frames) + 1)
        if frame:
            self._append(frame)

    def _append(self, frame: str) -> None:
        self.frames.append(frame)
        self._changed.set()
        self._changed = asyncio.Event()

    async def _collect(self, source: AsyncGenerator[str, None]) -> None:
        size = sum(len(frame.encode("utf-8")) for frame in self.frames)
        async with aclosing(source):
            async for line in source:
                frame = translate_legacy_line_to_sse(line, seq=len(self.frames) + 1)
                if not frame:
                    continue
                size += len(frame.encode("utf-8"))
                if size > MAX_REPLAY_BYTES:
                    raise ReplayTooLarge
                self.status = status_from_line(line, self.status)
                self._append(frame)

    def _finish(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            self.status = "cancelled"
            self._append_status("cancelled", "Task was cancelled")
        elif (error := task.exception()) is not None:
            self.status = "failed"
            logger.warning("Research stream failed (%s)", type(error).__name__)
            message = (
                "Research exceeded the event replay limit."
                if isinstance(error, ReplayTooLarge)
                else "Research stopped before it could finish."
            )
            self._append_status("error", message)
        if self.status == "running":
            self.status = "completed"
        self._append_line(run_status_line(self.status))
        self.completed_at = time.monotonic()
        self._changed.set()

    def _append_status(self, event: str, message: str) -> None:
        self._append(
            format_sse_event(
                event=event,
                data={"type": event, "data": {"message": message}},
                event_id=len(self.frames) + 1,
            )
        )

    async def subscribe(self, after: int = 0) -> AsyncGenerator[str, None]:
        while True:
            while after < len(self.frames):
                frame = self.frames[after]
                after += 1
                yield frame
            if self.completed_at is not None:
                return
            try:
                await asyncio.wait_for(self._changed.wait(), 15)
            except TimeoutError:
                yield format_sse_comment()


# shortcut: replay is local to one worker, use shared storage for multi-worker resumption.
_streams: dict[tuple[str, str], ResearchStream] = {}


def start_research_stream(
    key: tuple[str, str], thread_id: str, source: AsyncGenerator[str, None]
) -> ResearchStream:
    for saved_id in list(_streams):
        get_research_stream(saved_id)
    if len(_streams) >= MAX_STREAMS:
        evictable = next(
            (saved_id for saved_id, stream in _streams.items() if stream.completed_at is not None),
            None,
        )
        if evictable is None:
            raise ResearchStreamCapacity
        del _streams[evictable]

    stream = ResearchStream(thread_id, source)
    _streams[key] = stream
    return stream


def get_research_stream(key: tuple[str, str]) -> ResearchStream | None:
    stream = _streams.get(key)
    if (
        stream is not None
        and stream.completed_at is not None
        and time.monotonic() - stream.completed_at > REPLAY_SECONDS
    ):
        del _streams[key]
        return None
    return stream


def find_research_stream(thread_id: str):
    for key, stream in list(_streams.items()):
        if stream.thread_id == thread_id and get_research_stream(key) is not None:
            return key, stream
    return None


async def stop_research_streams() -> None:
    tasks = [stream.task for stream in _streams.values() if not stream.task.done()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    _streams.clear()
