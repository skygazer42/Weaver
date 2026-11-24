import asyncio
import os
import sys
from contextlib import aclosing
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from anyio import CancelScope, create_task_group, wait_all_tasks_blocked
from psycopg import AsyncConnection, sql
from psycopg.conninfo import make_conninfo

from common.durable_streams import DurableStreams
from common.research_streams import run_status_line
from common.run_journal import RunJournal


@pytest.fixture
def event_loop_policy():
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture
async def journal_dsn():
    dsn = os.environ.get("WEAVER_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set WEAVER_TEST_POSTGRES_DSN to run the PostgreSQL journal tests")

    schema = f"journal_test_{uuid4().hex}"
    async with await AsyncConnection.connect(dsn, autocommit=True) as connection:
        await connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield make_conninfo(dsn, options=f"-c search_path={schema}", application_name=schema)
        finally:
            await connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


@pytest_asyncio.fixture
async def journal(journal_dsn):
    journal = RunJournal(journal_dsn)
    await journal.setup()
    try:
        yield journal
    finally:
        await journal.close()


@pytest.mark.asyncio
async def test_worker_recovers_persisted_run_after_postgres_disconnect(journal, journal_dsn):
    run = await journal.submit("alice", "request", "thread-a", {})
    async with await AsyncConnection.connect(journal_dsn, autocommit=True) as control:
        killed = await control.execute(
            """SELECT pg_terminate_backend(pid, 1000) FROM pg_stat_activity
                WHERE application_name=%s AND pid <> pg_backend_pid()""",
            (control.info.parameter_status("application_name"),),
        )
        terminated = await killed.fetchall()
        assert terminated and all(row[0] for row in terminated)

    completed = run_status_line("completed")

    async def source(record):
        assert record.thread_id == run.thread_id
        yield completed

    streams = DurableStreams(journal, source)
    try:
        async with asyncio.timeout(10):
            async with aclosing(streams.subscribe(run)) as replay:
                frames = [frame async for frame in replay]
        assert '"status": "completed"' in "".join(frames)
        assert (await journal.get(run.owner, run.run_id)).status == "completed"
    finally:
        await streams.close()


@pytest.mark.asyncio
async def test_project_schedule_claim_is_atomic_and_skips_missed_intervals(journal, journal_dsn):
    first = datetime.now(UTC) - timedelta(days=16)
    await journal.create_project_schedule(
        "alice", "workspace", "schedule", {"workflow": "release-brief"}, 7, first
    )
    assert await journal.project_schedules("bob", "workspace") == []
    assert await journal.project_schedules("alice", "another") == []
    assert await journal.set_project_schedule_enabled("bob", "workspace", "schedule", False) is None
    [due] = await journal.due_project_schedules()
    second = RunJournal(journal_dsn)
    await second.setup()
    try:
        results = await asyncio.gather(
            journal.enqueue_project_schedule(due, "task-a", "thread-a", {"project_task": {}}),
            second.enqueue_project_schedule(due, "task-b", "thread-b", {"project_task": {}}),
        )
        [winner] = [run for run in results if run is not None]
        [plan] = await second.project_schedules("alice", "workspace")
        assert plan["last_task_id"] == winner.run_id.rsplit(":", 1)[1]
        assert plan["next_run_at"] == first + timedelta(days=21)
        assert await second.due_project_schedules() == []
        assert await second.delete_project_schedule("alice", "workspace", "schedule")
        assert await journal.get("alice", winner.run_id) == winner
    finally:
        await second.close()


@pytest.mark.asyncio
async def test_disconnected_subscriber_keeps_shared_postgres_connection_usable(
    journal, journal_dsn
):
    run = await journal.submit("alice", "request", "thread-a", {})
    attempt = await journal.claim(run.owner, run.run_id)
    assert attempt is not None
    completed = run_status_line("completed")
    assert await journal.finish(run.owner, run.run_id, attempt, "completed", final_line=completed)

    async def source(_record):
        yield completed

    streams = DurableStreams(journal, source)

    async def read_stream(*, task_status):
        with CancelScope() as scope:
            task_status.started(scope)
            async with aclosing(streams.subscribe(run)) as events:
                await anext(events)

    try:
        async with (
            await AsyncConnection.connect(journal_dsn, autocommit=True) as blocker,
            create_task_group() as clients,
        ):
            async with blocker.transaction():
                await blocker.execute("LOCK TABLE weaver_run_events IN ACCESS EXCLUSIVE MODE")
                client = await clients.start(read_stream)
                async with asyncio.timeout(5):
                    while True:
                        cursor = await blocker.execute("""SELECT EXISTS (
                            SELECT 1 FROM pg_locks
                            WHERE relation='weaver_run_events'::regclass AND NOT granted
                        )""")
                        if (await cursor.fetchone())[0]:
                            break
                        await asyncio.sleep(0.01)
                client.cancel()
                await wait_all_tasks_blocked()
        assert await journal.events_after(run.owner, run.run_id, 0) == [(1, completed)]
    finally:
        await streams.close()


@pytest.mark.asyncio
async def test_submit_keeps_first_payload_and_scopes_run_ids_by_owner(journal):
    alice = await journal.submit("alice", "request", "thread-a", {"query": "first"})
    duplicate = await journal.submit("alice", "request", "new-thread", {"query": "retry"})
    bob = await journal.submit("bob", "request", "thread-b", {"query": "other"})

    assert duplicate == alice
    assert alice.thread_id == "thread-a"
    assert alice.payload == {"query": "first"}
    assert alice.status == "queued"
    assert await journal.get_by_thread("thread-a") == alice
    assert await journal.get_by_thread("new-thread") is None
    assert await journal.get("bob", "request") == bob
    assert await journal.get("carol", "request") is None
    attempt = await journal.claim("alice", "request")
    assert attempt is not None
    assert await journal.append("bob", "request", attempt, "wrong owner") is None
    assert await journal.append("alice", "request", attempt, '0:"first"\n') == 1
    assert await journal.events_after("bob", "request", 0) == []
    assert await journal.events_after("alice", "request", 0) == [(1, '0:"first"\n')]


@pytest.mark.asyncio
async def test_recovery_fences_expired_attempt_and_keeps_durable_event_sequence(
    journal, journal_dsn
):
    run = await journal.submit("alice", "request", "thread-a", {"query": "first"})
    restarted = RunJournal(journal_dsn)
    await restarted.setup()
    try:
        attempts = await asyncio.gather(
            journal.claim("alice", "request"), restarted.claim("alice", "request")
        )
        (attempt,) = [attempt for attempt in attempts if attempt is not None]
        assert await journal.renew("alice", "request", attempt)
        assert await journal.runnable(10) == []
        assert await journal.append("alice", "request", attempt, "first") == 1

        await journal.close()
        async with await AsyncConnection.connect(journal_dsn, autocommit=True) as connection:
            await connection.execute(
                "UPDATE weaver_runs SET lease_until = clock_timestamp() - interval '1 second'"
            )

        assert await restarted.append("alice", "request", attempt, "stale") is None
        assert not await restarted.renew("alice", "request", attempt)
        assert not await restarted.finish("alice", "request", attempt, "failed")
        [recoverable] = await restarted.runnable(10)
        assert recoverable.thread_id == run.thread_id
        assert recoverable.payload == {"query": "first"}
        recovered_attempt = await restarted.claim("alice", "request")
        assert recovered_attempt is not None and recovered_attempt != attempt
        assert await restarted.append("alice", "request", attempt, "stale") is None
        assert await restarted.append("alice", "request", recovered_attempt, "second") == 2
        assert await restarted.finish(
            "alice", "request", recovered_attempt, "completed", final_line="complete"
        )
        assert await restarted.events_after("alice", "request", 1) == [
            (2, "second"),
            (3, "complete"),
        ]
        assert (await restarted.get("alice", "request")).status == "completed"
        assert await restarted.runnable(10) == []
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_requeue_is_a_single_transition_and_preserves_approval_for_recovery(journal):
    await journal.submit("alice", "request", "thread-a", {"query": "first"})
    attempt = await journal.claim("alice", "request")
    assert attempt is not None
    assert await journal.finish("alice", "request", attempt, "awaiting_approval")

    assert await journal.requeue("alice", "request", payload_update={"approval": "approved"})
    assert not await journal.requeue("alice", "request", payload_update={"approval": "denied"})
    [run] = await journal.runnable(10)
    assert run.status == "queued"
    assert run.thread_id == "thread-a"
    assert run.payload == {"query": "first", "approval": "approved"}


@pytest.mark.asyncio
async def test_conversation_turns_use_only_the_owners_committed_reports(journal):
    import json

    for owner, run_id, answer in (
        ("alice", "first", "First"),
        ("alice", "second", "Second"),
        ("bob", "first", "Private"),
    ):
        request = {
            "conversation_id": "shared-id",
            "messages": [{"role": "user", "content": f"Ask {answer}"}],
        }
        await journal.submit(owner, run_id, f"{owner}-{run_id}", {"request": request})
        attempt = await journal.claim(owner, run_id)
        assert attempt is not None
        frame = "0:" + json.dumps({"type": "completion", "data": {"content": answer}}) + "\n"
        await journal.append(owner, run_id, attempt, frame)
        await journal.finish(owner, run_id, attempt, "completed")
    turns = await journal.conversation_turns("alice", "shared-id")
    assert [answer for _, answer in turns] == ["First", "Second"]
    assert [messages[-1]["content"] for messages, _ in turns] == ["Ask First", "Ask Second"]


@pytest.mark.asyncio
async def test_cancel_is_owner_scoped_and_persists_worker_intent(journal):
    await journal.submit("alice", "running", "thread-a", {})
    await journal.submit("alice", "queued", "thread-b", {})
    attempt = await journal.claim("alice", "running")
    assert attempt is not None

    assert not await journal.request_cancel("bob", "running")
    assert await journal.request_cancel("alice", "running")
    run = await journal.get("alice", "running")
    assert run.status == "running" and run.cancel_requested
    assert not await journal.finish("alice", "running", attempt, "completed")
    assert await journal.finish("alice", "running", attempt, "cancelled", final_line="cancelled")
    assert await journal.events_after("alice", "running", 0) == [(1, "cancelled")]

    assert await journal.request_cancel("alice", "queued", final_line="cancelled")
    queued = await journal.get("alice", "queued")
    assert queued.status == "cancelled" and queued.cancel_requested
    assert await journal.events_after("alice", "queued", 0) == [(1, "cancelled")]
    assert not await journal.request_cancel("alice", "queued", final_line="cancelled")
    assert await journal.claim("alice", "queued") is None
