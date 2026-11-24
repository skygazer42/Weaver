"""Persist owner-scoped research runs and their SSE replay events."""

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Jsonb

_RUN_FIELDS = "owner, run_id, thread_id, payload, status, cancel_requested, event_seq"
_RUNNABLE = """status IN ('queued', 'running')
    AND (status = 'queued' OR lease_until <= clock_timestamp())"""
_ACTIVE_ATTEMPT = """owner = %(owner)s AND run_id = %(run_id)s AND attempt = %(attempt)s
    AND status = 'running' AND lease_until > clock_timestamp()"""
_FINISH_STATUSES = {
    "awaiting_approval",
    "completed",
    "failed",
    "cancelled",
    "insufficient_evidence",
}


@dataclass(frozen=True)
class RunRecord:
    owner: str
    run_id: str
    thread_id: str
    payload: dict[str, Any]
    status: str
    cancel_requested: bool
    event_seq: int


class RunJournal:
    """An application-owned PostgreSQL connection with atomic run transitions."""

    def __init__(self, dsn: str, *, lease_seconds: float = 30) -> None:
        self._dsn = dsn
        self._lease_seconds = lease_seconds
        self._connection: AsyncConnection[DictRow] | None = None

    async def setup(self) -> None:
        if self._connection is not None:
            return
        connection = await AsyncConnection.connect(self._dsn, autocommit=True, row_factory=dict_row)
        try:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtext('weaver_run_journal'))"
                )
                await connection.execute("""
                    CREATE TABLE IF NOT EXISTS weaver_runs (
                        owner TEXT NOT NULL,
                        run_id TEXT NOT NULL,
                        thread_id TEXT NOT NULL UNIQUE,
                        payload JSONB NOT NULL,
                        status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
                            'queued', 'running', 'awaiting_approval', 'completed', 'failed',
                            'cancelled', 'insufficient_evidence'
                        )),
                        cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
                        attempt TEXT,
                        lease_until TIMESTAMPTZ,
                        event_seq BIGINT NOT NULL DEFAULT 0,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                        PRIMARY KEY (owner, run_id)
                    );
                    CREATE INDEX IF NOT EXISTS weaver_runs_runnable
                        ON weaver_runs (created_at, owner, run_id)
                        WHERE status IN ('queued', 'running');
                    CREATE INDEX IF NOT EXISTS weaver_runs_workspace
                        ON weaver_runs (owner, (payload->>'workspace_id'), created_at DESC)
                        WHERE payload ? 'project_task';
                    CREATE TABLE IF NOT EXISTS weaver_run_events (
                        owner TEXT NOT NULL,
                        run_id TEXT NOT NULL,
                        seq BIGINT NOT NULL,
                        raw_line TEXT NOT NULL,
                        PRIMARY KEY (owner, run_id, seq),
                        FOREIGN KEY (owner, run_id) REFERENCES weaver_runs (owner, run_id)
                            ON DELETE CASCADE
                    );
                """)
        except BaseException:
            await connection.close()
            raise
        self._connection = connection

    async def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            await connection.close()

    @property
    def _db(self) -> AsyncConnection[DictRow]:
        if self._connection is None:
            raise RuntimeError("Run journal is closed")
        return self._connection

    async def submit(
        self, owner: str, run_id: str, thread_id: str, payload: dict[str, Any]
    ) -> RunRecord:
        cursor = await self._db.execute(
            f"""INSERT INTO weaver_runs (owner, run_id, thread_id, payload)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (owner, run_id) DO UPDATE SET run_id = weaver_runs.run_id
                RETURNING {_RUN_FIELDS}""",
            (owner, run_id, thread_id, Jsonb(payload)),
        )
        row = await cursor.fetchone()
        assert row is not None
        return RunRecord(**row)

    async def get(self, owner: str, run_id: str) -> RunRecord | None:
        cursor = await self._db.execute(
            f"SELECT {_RUN_FIELDS} FROM weaver_runs WHERE owner = %s AND run_id = %s",
            (owner, run_id),
        )
        row = await cursor.fetchone()
        return RunRecord(**row) if row is not None else None

    async def get_by_thread(self, thread_id: str) -> RunRecord | None:
        """Look up a graph thread for backend ownership checks."""
        cursor = await self._db.execute(
            f"SELECT {_RUN_FIELDS} FROM weaver_runs WHERE thread_id = %s", (thread_id,)
        )
        row = await cursor.fetchone()
        return RunRecord(**row) if row is not None else None

    async def conversation_turns(
        self, owner: str, conversation_id: str, *, workspace_id: str | None = None
    ) -> list[tuple[list, str]]:
        """Return the most recent committed turns in transcript order."""
        cursor = await self._db.execute(
            """SELECT recent.messages, completion.answer
                FROM (
                    SELECT owner, run_id, created_at, payload->'request'->'messages' AS messages
                    FROM weaver_runs
                    WHERE owner=%s AND status='completed'
                        AND payload->'request'->>'conversation_id'=%s
                        AND payload->'request'->>'workspace_id' IS NOT DISTINCT FROM %s
                    ORDER BY created_at DESC LIMIT 16
                ) recent
                JOIN LATERAL (
                    SELECT substring(raw_line from 3)::jsonb->'data'->>'content' AS answer
                    FROM weaver_run_events
                    WHERE owner=recent.owner AND run_id=recent.run_id
                        AND substring(raw_line from 3)::jsonb->>'type' = 'completion'
                    ORDER BY seq DESC LIMIT 1
                ) completion ON completion.answer IS NOT NULL
                ORDER BY recent.created_at""",
            (owner, conversation_id, workspace_id),
        )
        return [(row["messages"], row["answer"]) for row in await cursor.fetchall()]

    async def project_tasks(self, owner: str, workspace_id: str) -> list[dict]:
        cursor = await self._db.execute(
            """SELECT r.thread_id, r.status, r.created_at, r.payload->'project_task' AS task,
                       CASE WHEN r.status='failed' THEN e.raw_line END AS error_event
                FROM weaver_runs r
                LEFT JOIN weaver_run_events e
                    ON r.status='failed' AND e.owner=r.owner AND e.run_id=r.run_id
                    AND e.seq=r.event_seq-1
                WHERE r.owner=%s AND r.payload->>'workspace_id'=%s AND r.payload ? 'project_task'
                ORDER BY r.created_at DESC, r.run_id""",
            (owner, workspace_id),
        )
        return await cursor.fetchall()

    async def project_deliverables(
        self,
        owner: str,
        workspace_id: str,
        *,
        thread_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        cursor = await self._db.execute(
            """SELECT substring(e.raw_line from 3)::jsonb->'data' AS artifact
                FROM weaver_runs r
                JOIN weaver_run_events e
                    ON e.owner=r.owner AND e.run_id=r.run_id AND e.seq=r.event_seq-1
                WHERE r.owner=%s AND r.payload->>'workspace_id'=%s AND r.payload ? 'project_task'
                    AND r.status='completed' AND (%s::text IS NULL OR r.thread_id=%s)
                    AND substring(e.raw_line from 3)::jsonb->>'type'='artifact'
                ORDER BY r.created_at DESC, r.run_id LIMIT %s""",
            (owner, workspace_id, thread_id, thread_id, limit),
        )
        return [row["artifact"] for row in await cursor.fetchall()]

    async def runnable(self, limit: int) -> list[RunRecord]:
        cursor = await self._db.execute(
            f"""SELECT {_RUN_FIELDS} FROM weaver_runs WHERE {_RUNNABLE}
                ORDER BY created_at, owner, run_id LIMIT %s""",
            (limit,),
        )
        return [RunRecord(**row) for row in await cursor.fetchall()]

    async def claim(self, owner: str, run_id: str) -> str | None:
        attempt = uuid4().hex
        cursor = await self._db.execute(
            f"""UPDATE weaver_runs SET status = 'running', attempt = %s,
                lease_until = clock_timestamp() + %s * interval '1 second'
                WHERE owner = %s AND run_id = %s AND {_RUNNABLE}""",
            (attempt, self._lease_seconds, owner, run_id),
        )
        return attempt if cursor.rowcount else None

    async def renew(self, owner: str, run_id: str, attempt: str) -> bool:
        cursor = await self._db.execute(
            f"""UPDATE weaver_runs
                SET lease_until = clock_timestamp() + %(lease_seconds)s * interval '1 second'
                WHERE {_ACTIVE_ATTEMPT}""",
            {
                "owner": owner,
                "run_id": run_id,
                "attempt": attempt,
                "lease_seconds": self._lease_seconds,
            },
        )
        return cursor.rowcount > 0

    async def append(
        self, owner: str, run_id: str, attempt: str, raw_legacy_line: str
    ) -> int | None:
        cursor = await self._db.execute(
            f"""WITH next_event AS (
                    UPDATE weaver_runs SET event_seq = event_seq + 1
                    WHERE {_ACTIVE_ATTEMPT} RETURNING owner, run_id, event_seq
                )
                INSERT INTO weaver_run_events (owner, run_id, seq, raw_line)
                SELECT owner, run_id, event_seq, %(line)s FROM next_event RETURNING seq""",
            {"owner": owner, "run_id": run_id, "attempt": attempt, "line": raw_legacy_line},
        )
        row = await cursor.fetchone()
        return row["seq"] if row is not None else None

    async def events_after(self, owner: str, run_id: str, after: int) -> list[tuple[int, str]]:
        cursor = await self._db.execute(
            """SELECT seq, raw_line FROM weaver_run_events
                WHERE owner = %s AND run_id = %s AND seq > %s ORDER BY seq""",
            (owner, run_id, after),
        )
        return [(row["seq"], row["raw_line"]) for row in await cursor.fetchall()]

    async def finish(
        self,
        owner: str,
        run_id: str,
        attempt: str,
        status: str,
        *,
        final_line: str | None = None,
        artifact_line: str | None = None,
    ) -> bool:
        """Transition this attempt and commit its final replay frame together."""
        if status not in _FINISH_STATUSES:
            raise ValueError(f"Invalid finish status: {status}")
        cursor = await self._db.execute(
            f"""WITH finished AS (
                    UPDATE weaver_runs SET status = %(status)s, attempt = NULL, lease_until = NULL,
                        event_seq = event_seq
                            + (%(line)s::text IS NOT NULL)::int
                            + (%(artifact)s::text IS NOT NULL)::int
                    WHERE {_ACTIVE_ATTEMPT} AND (NOT cancel_requested OR %(status)s = 'cancelled')
                    RETURNING owner, run_id, event_seq
                ), final_event AS (
                    INSERT INTO weaver_run_events (owner, run_id, seq, raw_line)
                    SELECT owner, run_id, event_seq, %(line)s FROM finished WHERE %(line)s::text IS NOT NULL
                    UNION ALL
                    SELECT owner, run_id, event_seq - (%(line)s::text IS NOT NULL)::int, %(artifact)s
                    FROM finished WHERE %(artifact)s::text IS NOT NULL
                )
                SELECT 1 FROM finished""",
            {
                "owner": owner,
                "run_id": run_id,
                "attempt": attempt,
                "status": status,
                "line": final_line,
                "artifact": artifact_line,
            },
        )
        return await cursor.fetchone() is not None

    async def requeue(
        self,
        owner: str,
        run_id: str,
        *,
        payload_update: dict[str, Any] | None = None,
        expected_seq: int | None = None,
    ) -> bool:
        cursor = await self._db.execute(
            """UPDATE weaver_runs SET status = 'queued', payload = payload || %s
                WHERE owner = %s AND run_id = %s AND status = 'awaiting_approval'
                    AND NOT cancel_requested AND (%s::bigint IS NULL OR event_seq=%s)""",
            (Jsonb(payload_update or {}), owner, run_id, expected_seq, expected_seq),
        )
        return cursor.rowcount > 0

    async def request_cancel(
        self, owner: str, run_id: str, *, final_line: str | None = None
    ) -> bool:
        """Cancel an idle run immediately or record cancellation for its worker."""
        cursor = await self._db.execute(
            """WITH updated AS (
                    UPDATE weaver_runs SET cancel_requested = TRUE,
                        status = CASE WHEN status = 'running' THEN status ELSE 'cancelled' END,
                        event_seq = event_seq + CASE
                            WHEN status <> 'running' AND %(line)s::text IS NOT NULL THEN 1 ELSE 0 END
                    WHERE owner = %(owner)s AND run_id = %(run_id)s
                        AND status IN ('queued', 'running', 'awaiting_approval')
                    RETURNING owner, run_id, event_seq, status
                ), final_event AS (
                    INSERT INTO weaver_run_events (owner, run_id, seq, raw_line)
                    SELECT owner, run_id, event_seq, %(line)s FROM updated
                    WHERE status = 'cancelled' AND %(line)s IS NOT NULL
                )
                SELECT 1 FROM updated""",
            {"owner": owner, "run_id": run_id, "line": final_line},
        )
        return await cursor.fetchone() is not None
