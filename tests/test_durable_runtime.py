"""Verify the real SSE runtime across an abrupt API process exit."""

import os
import subprocess
import sys
import time
from contextlib import contextmanager
from uuid import uuid4

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

_WORKER = """
import asyncio
import os
import threading
from pathlib import Path

if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn
from langgraph.graph import END, START, StateGraph
from agent.core.state import AgentState
from agent.workflows.deepsearch_optimized import _research_step
from common.run_journal import RunJournal
import main
print("Fixture worker imported the app.", flush=True)

root = Path(os.environ["WEAVER_DATA_DIR"])
first = os.environ["WEAVER_TEST_FIRST_WORKER"] == "1"
main.settings.internal_api_key = ""
main.RunJournal = lambda dsn: RunJournal(dsn, lease_seconds=4)
main._store_search = lambda *args, **kwargs: []
main.fetch_memories = lambda *args, **kwargs: []
main.store_interaction = lambda *args, **kwargs: True

async def noop():
    pass

main.startup_event = noop
main.shutdown_event = noop

def _fixture_search(topic):
    with (root / "searches.log").open("a", encoding="utf-8") as output:
        output.write(topic + "\\n")
    return [{"url": "https://example.invalid/fixture", "title": "Fixture evidence"}]

def research(state, config):
    results = _research_step(config, _fixture_search, state["input"])
    if first and state["input"] == "after-search":
        (root / "saved-search").touch()
        threading.Event().wait()
    return {
        "route": "deep",
        "final_report": "Recovered with a checkpoint.",
        "is_complete": True,
        "scraped_content": results,
    }

def configure(saver):
    main.checkpointer = saver
    graph = StateGraph(AgentState)
    graph.add_node("deepsearch", research)
    graph.add_edge(START, "deepsearch")
    graph.add_edge("deepsearch", END)
    main.research_graph = graph.compile(checkpointer=saver)

main._configure_graphs = configure
saved_source = main._saved_run_source

async def source(thread_id, saved, *, durable):
    if first and saved["request"]["messages"][-1]["content"] == "before-checkpoint":
        (root / "before-checkpoint").touch()
        await asyncio.Future()
    async for line in saved_source(thread_id, saved, durable=durable):
        yield line

main._saved_run_source = source
class FixtureServer(uvicorn.Server):
    async def startup(self, sockets=None):
        await super().startup(sockets)
        if self.started:
            address = self.servers[0].sockets[0].getsockname()
            (root / ("first.port" if first else "second.port")).write_text(str(address[1]))

server = FixtureServer(uvicorn.Config(
    main.app, host="127.0.0.1", port=0, log_level="info",
))
asyncio.run(server.serve())
"""


def _until(predicate, *, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.2)
    pytest.fail("Timed out waiting for the fixture condition")


@contextmanager
def _worker(dsn, tmp_path, *, first):
    label = "first" if first else "second"
    port_file = tmp_path / f"{label}.port"
    env = {
        **os.environ,
        "APP_ENV": "production",
        "DATABASE_URL": dsn,
        "OPENAI_API_KEY": "fixture",
        "SILICONFLOW_API_KEY": "",
        "ENABLE_MCP": "false",
        "ENABLE_FILE_LOGGING": "false",
        "LOG_FORMAT": "%(message)s",
        "MEMORY_STORE_BACKEND": "memory",
        "WEAVER_DATA_DIR": str(tmp_path),
        "WEAVER_TEST_FIRST_WORKER": str(int(first)),
    }
    log_path = tmp_path / f"worker-{label}.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-B", "-u", "-c", _WORKER],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        def ready():
            if process.poll() is not None:
                pytest.fail(log_path.read_text(encoding="utf-8", errors="replace"))
            return port_file.is_file() and port_file.stat().st_size > 0

        try:
            _until(ready)
            port = int(port_file.read_text())
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", timeout=45, trust_env=False
            ) as client:
                yield client, process
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)


def _submit(client, label):
    run_id = uuid4().hex
    with client.stream(
        "POST",
        f"/api/chat/sse?research_id={run_id}",
        json={"messages": [{"role": "user", "content": label}], "search_mode": "deep"},
    ) as response:
        assert response.status_code == 200
        return run_id, response.headers["X-Thread-ID"]


def test_runtime_resumes_before_checkpoint_and_after_saved_search(tmp_path):
    dsn = os.getenv("WEAVER_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set WEAVER_TEST_POSTGRES_DSN to a disposable PostgreSQL database")
    schema = "weaver_runtime_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as db:
        db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            test_dsn = make_conninfo(dsn, options=f"-c search_path={schema}")
            with psycopg.connect(test_dsn, autocommit=True) as isolated:
                with _worker(test_dsn, tmp_path, first=True) as (first, process):
                    early_id, early_thread = _submit(first, "before-checkpoint")
                    saved_id, saved_thread = _submit(first, "after-search")
                    _until(lambda: (tmp_path / "before-checkpoint").exists())
                    _until(lambda: (tmp_path / "saved-search").exists())
                    _until(
                        lambda: (
                            isolated.execute(
                                "SELECT 1 FROM checkpoint_writes WHERE thread_id=%s AND channel='__return__'",
                                (saved_thread,),
                            ).fetchone()
                            is not None
                        )
                    )
                    assert (
                        isolated.execute(
                            "SELECT 1 FROM checkpoints WHERE thread_id=%s", (early_thread,)
                        ).fetchone()
                        is None
                    )
                    process.kill()
                    process.wait(timeout=10)
                with _worker(test_dsn, tmp_path, first=False) as (second, _):
                    for run_id, thread_id in ((early_id, early_thread), (saved_id, saved_thread)):
                        recovered = second.get(
                            f"/api/chat/sse/{run_id}", headers={"Last-Event-ID": "1"}
                        )
                        assert recovered.headers["X-Thread-ID"] == thread_id
                        assert "Recovered with a checkpoint." in recovered.text
                        assert (
                            '"status":"completed"' in recovered.text
                            or '"status": "completed"' in recovered.text
                        )
                        ids = [
                            int(line[4:])
                            for line in recovered.text.splitlines()
                            if line.startswith("id: ")
                        ]
                        assert ids == list(range(2, 2 + len(ids)))
                assert sorted((tmp_path / "searches.log").read_text().splitlines()) == [
                    "after-search",
                    "before-checkpoint",
                ]
        finally:
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
