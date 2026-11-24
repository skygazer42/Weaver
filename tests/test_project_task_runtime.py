import asyncio
import json
import os
from uuid import uuid4

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo


def test_project_task_replay_revision_and_ownership(monkeypatch, tmp_path):
    dsn = os.getenv("WEAVER_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set WEAVER_TEST_POSTGRES_DSN to test the project task runtime")

    from langchain_core.messages import AIMessage

    import main
    from workbench import project_workflows

    schema = f"project_test_{uuid4().hex}"
    monkeypatch.setenv("WEAVER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(main.settings, "internal_api_key", "project-fixture")
    monkeypatch.setattr(main.settings, "auth_user_header", "X-Weaver-User")
    monkeypatch.setattr(main.settings, "openai_api_key", "fixture")
    monkeypatch.setattr(
        main.settings, "database_url", make_conninfo(dsn, options=f"-c search_path={schema}")
    )

    async def noop():
        pass

    monkeypatch.setattr(main, "startup_event", noop)
    monkeypatch.setattr(main, "shutdown_event", noop)
    calls = []

    class Model:
        def bind(self, **_kwargs):
            return self

        async def ainvoke(self, messages):
            calls.append(str(messages))
            title = (
                "Revised project specification"
                if "Tighten export checks" in calls[-1]
                else "Project specification"
            )
            output = {
                "title": title,
                "language": "en",
                "requirements": [
                    {
                        "text": "Include totals in monthly exports.",
                        "acceptance": ["Check the exported totals."],
                        "citations": [
                            {"source": "S1", "quote": "Monthly exports must include totals."}
                        ],
                    }
                ],
                "assumptions": [],
                "open_questions": [],
            }
            return AIMessage(content=json.dumps(output))

    monkeypatch.setattr(project_workflows, "create_chat_model", lambda *_args, **_kwargs: Model())

    async def check():
        auth = {"Authorization": "Bearer project-fixture", "X-Weaver-User": "alice"}
        outsider = {**auth, "X-Weaver-User": "bob"}
        transport = httpx.ASGITransport(app=main.app)
        async with (
            main.lifespan(main.app),
            httpx.AsyncClient(
                transport=transport, base_url="http://weaver.test", headers=auth
            ) as client,
        ):
            workspace = (await client.post("/api/workspaces")).json()
            another = (await client.post("/api/workspaces")).json()
            path = f"/api/workspaces/{workspace['id']}"
            other_path = f"/api/workspaces/{another['id']}"
            metadata = {
                "instructions": "Use the product team's terminology.",
                "decisions": "We publish once a month.",
            }
            assert (await client.patch(path, json=metadata)).status_code == 200
            saved = await client.post(
                path + "/files",
                files={"file": ("interviews.md", b"Monthly exports must include totals.")},
            )
            assert saved.status_code == 201
            file_id = saved.json()["id"]
            payload = {
                "workflow": "requirements-spec",
                "request_id": uuid4().hex,
                "prompt": "Write a Spec",
                "file_ids": [file_id],
            }
            assert (await client.post(other_path + "/tasks", json=payload)).status_code == 404
            first = await client.post(path + "/tasks", json=payload)
            assert first.status_code == 202, first.text
            task_id = first.json()["id"]
            replay = await client.get(path + f"/tasks/{task_id}/events")
            first_events = [
                int(line[4:]) for line in replay.text.splitlines() if line.startswith("id: ")
            ]
            assert first_events and first_events == sorted(set(first_events))
            assert "event: artifact" in replay.text and '"status": "completed"' in replay.text
            duplicate = await client.post(path + "/tasks", json=payload)
            assert duplicate.json()["id"] == task_id
            assert len(calls) == 1 and "We publish once a month." in calls[0]
            end = await client.get(
                path + f"/tasks/{task_id}/events",
                headers={**auth, "Last-Event-ID": str(first_events[-2])},
            )
            assert f"id: {first_events[-1]}" in end.text and "event: artifact" not in end.text
            assert (
                await client.get(path + f"/tasks/{task_id}/events", headers=outsider)
            ).status_code == 404
            assert (await client.get(other_path + f"/tasks/{task_id}/events")).status_code == 404
            assert (await client.get(f"/api/chat/sse/{task_id}")).status_code == 404
            [artifact] = (await client.get(path + "/deliverables")).json()
            download = path + f"/deliverables/{artifact['id']}/download"
            assert "Include totals" in (await client.get(download)).text
            assert (await client.get(download, headers=outsider)).status_code == 404
            assert artifact["sources"][0]["url"] == path + f"/files/{file_id}"
            assert (
                await client.get(artifact["sources"][0]["url"])
            ).text == "Monthly exports must include totals."
            follow = await client.post(
                path + "/tasks",
                json={
                    "workflow": "requirements-spec",
                    "request_id": uuid4().hex,
                    "prompt": "Tighten export checks",
                    "artifact_id": artifact["id"],
                },
            )
            assert follow.status_code == 202, follow.text
            await client.get(path + f"/tasks/{follow.json()['id']}/events")
            assert "Project specification" in calls[-1]
            revised, original = (await client.get(path + "/deliverables")).json()
            assert revised["based_on"] == original["id"] == artifact["id"]
        async with (
            main.lifespan(main.app),
            httpx.AsyncClient(
                transport=transport, base_url="http://weaver.test", headers=auth
            ) as client,
        ):
            assert (await client.get(download)).status_code == 200
            assert len((await client.get(path + "/tasks")).json()) == 2
            assert len(calls) == 2

    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            if os.name == "nt":
                with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                    runner.run(check())
            else:
                asyncio.run(check())
        finally:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
