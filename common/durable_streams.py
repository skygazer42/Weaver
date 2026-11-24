"""Claim durable runs, publish replay events and cancel work across API processes."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing

from anyio import CancelScope
from psycopg import OperationalError

from common.chat_stream_translate import translate_legacy_line_to_sse
from common.research_streams import MAX_STREAMS, run_status_line, status_from_line
from common.run_journal import RunJournal, RunRecord
from common.sse import format_sse_comment

logger = logging.getLogger(__name__)
_ACTIVE = {"queued", "running"}


class DurableStreams:
    def __init__(
        self,
        journal: RunJournal,
        source: Callable[[RunRecord], AsyncGenerator[str, None]],
        *,
        enqueue_due: Callable[[RunJournal], Awaitable[None]] | None = None,
    ) -> None:
        self.journal = journal
        self.source = source
        self._enqueue_due = enqueue_due
        self._tasks: dict[tuple[str, str], asyncio.Task] = {}
        self._closing = False
        self._poller = asyncio.create_task(self._poll())

    def schedule(self, record: RunRecord) -> None:
        key = (record.owner, record.run_id)
        if not self._closing and key not in self._tasks and len(self._tasks) < MAX_STREAMS:
            task = asyncio.create_task(self._run(record))
            self._tasks[key] = task
            task.add_done_callback(lambda _: self._tasks.pop(key, None))

    async def _poll(self) -> None:
        while True:
            if self._enqueue_due is not None:
                try:
                    await self._enqueue_due(self.journal)
                except Exception:
                    logger.exception("Could not enqueue scheduled project tasks")
            try:
                for record in await self.journal.runnable(MAX_STREAMS):
                    self.schedule(record)
            except Exception:
                logger.exception("Could not poll durable runs")
            await asyncio.sleep(1)

    async def _run(self, record: RunRecord) -> None:
        try:
            attempt = await self.journal.claim(record.owner, record.run_id)
            if attempt is not None:
                await self._execute(record, attempt)
        except Exception:
            logger.exception("Durable run %s stopped before committing its result", record.run_id)

    async def _execute(self, record: RunRecord, attempt: str) -> None:
        key = (record.owner, record.run_id)
        current = await self.journal.get(*key)
        if current and current.cancel_requested:
            await self.journal.finish(
                *key, attempt, "cancelled", final_line=run_status_line("cancelled")
            )
            return
        if current is None:
            return
        if await self.journal.append(*key, attempt, run_status_line("running")) is None:
            return
        state = "completed"
        artifact = None
        work = asyncio.create_task(self._write_events(current, attempt))
        monitor = asyncio.create_task(self._monitor(record, attempt, work))
        try:
            state, artifact = await work
        except asyncio.CancelledError:
            if self._closing:
                raise
            current = await self.journal.get(*key)
            if current is None or not current.cancel_requested:
                return
            state = "cancelled"
        except OperationalError:
            # The lease lets another attempt recover after a database connection failure.
            raise
        except Exception:
            logger.exception("Durable run %s failed", record.run_id)
            state = "failed"
        finally:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
        if not self._closing and not await self.journal.finish(
            *key,
            attempt,
            state,
            final_line=run_status_line(state),
            artifact_line=artifact if state == "completed" else None,
        ):
            current = await self.journal.get(*key)
            if current and current.cancel_requested:
                await self.journal.finish(
                    *key, attempt, "cancelled", final_line=run_status_line("cancelled")
                )

    async def _write_events(self, record: RunRecord, attempt: str) -> tuple[str, str | None]:
        state = "completed"
        artifact = None
        async with aclosing(self.source(record)) as source:
            async for line in source:
                if self._closing:
                    break
                if line.startswith("0:"):
                    if (
                        record.payload.get("project_task")
                        and json.loads(line[2:]).get("type") == "artifact"
                    ):
                        artifact = line
                        continue
                    seq = await self.journal.append(record.owner, record.run_id, attempt, line)
                    if seq is None:
                        break
                    state = status_from_line(line, state)
        return state, artifact

    async def _monitor(self, record: RunRecord, attempt: str, task: asyncio.Task) -> None:
        key = (record.owner, record.run_id)
        try:
            while not task.done():
                await asyncio.sleep(1)
                row = await self.journal.get(*key)
                if (
                    row is None
                    or row.cancel_requested
                    or not await self.journal.renew(*key, attempt)
                ):
                    task.cancel()
                    return
        except Exception:
            task.cancel()
            logger.exception("Could not renew durable run %s", record.run_id)

    async def subscribe(self, record: RunRecord, after: int = 0):
        key = (record.owner, record.run_id)
        keepalive_at = time.monotonic()
        while True:
            # Let in-flight reads finish on the shared connection when an SSE client disconnects.
            with CancelScope(shield=True):
                row = await self.journal.get(*key)
                events = await self.journal.events_after(*key, after)
            for seq, line in events:
                after = seq
                frame = translate_legacy_line_to_sse(line, seq=seq)
                if frame:
                    yield frame
                    keepalive_at = time.monotonic()
            if row is None or row.status not in _ACTIVE:
                return
            if time.monotonic() - keepalive_at >= 15:
                yield format_sse_comment()
                keepalive_at = time.monotonic()
            await asyncio.sleep(0.2)

    async def close(self) -> None:
        self._closing = True
        tasks = [self._poller, *self._tasks.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
