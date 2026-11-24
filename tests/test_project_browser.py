"""Exercise the production Web build against Weaver and disposable PostgreSQL."""

import asyncio
import json
import os
import re
import subprocess
from base64 import b64encode
from threading import Event, Thread
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import psycopg
import pytest
import uvicorn
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from playwright.sync_api import expect, sync_playwright
from psycopg import sql
from psycopg.conninfo import make_conninfo

from scripts.web_e2e import WEB, free_port, stop_app, wait_until_listening

AUTH = {"Authorization": "Bearer project-browser-fixture", "X-Weaver-User": "alice"}
INTERVIEW = "Monthly exports must include totals."
DOC = "The report header must show the reporting period."
DECISION = "The operations team publishes monthly."
UPDATED_DECISION = "The operations team publishes after the security review."
SCHEDULE_PROMPT = "Summarize the latest release every week."
RELEASE = "Account export is available."
README = "Run planner migrate before upgrading."


def test_project_workflows_and_chat_across_browser_sessions(monkeypatch, tmp_path):
    if os.getenv("WEAVER_PROJECT_BROWSER_E2E") != "1":
        pytest.skip("Set WEAVER_PROJECT_BROWSER_E2E=1 after building the Web app")
    dsn = os.environ["WEAVER_TEST_POSTGRES_DSN"]
    assert (WEB / ".next" / "BUILD_ID").is_file()

    import main
    from agent.workflows import agent_factory
    from workbench import project_workflows

    schema = "project_browser_" + uuid4().hex
    monkeypatch.setenv("WEAVER_DATA_DIR", str(tmp_path))
    settings = main.settings
    monkeypatch.setattr(settings, "internal_api_key", "project-browser-fixture")
    monkeypatch.setattr(settings, "auth_user_header", "X-Weaver-User")
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "siliconflow_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "fixture")
    monkeypatch.setattr(settings, "primary_model", "fixture-model")
    monkeypatch.setattr(settings, "tool_selector", False)
    monkeypatch.setattr(settings, "enable_file_logging", False)
    monkeypatch.setattr(
        settings, "database_url", make_conninfo(dsn, options=f"-c search_path={schema}")
    )

    async def noop():
        pass

    monkeypatch.setattr(main, "startup_event", noop)
    monkeypatch.setattr(main, "shutdown_event", noop)
    workflow_requests = []
    chat_contexts = []
    github_calls = []
    draft_started = Event()
    release_draft = Event()

    def statement(text, source, quote):
        return {"text": text, "citations": [{"source": source, "quote": quote}]}

    class WorkflowModel:
        def bind(self, **_kwargs):
            return self

        async def ainvoke(self, messages):
            request = json.loads(messages[-1].content)
            workflow_requests.append(request)
            if request["prompt"] == "Draft the monthly export spec.":
                draft_started.set()
                async with asyncio.timeout(25):
                    while not release_draft.is_set():
                        await asyncio.sleep(0.05)
            if request["sources"][0]["kind"] == "github_release":
                scheduled = request["prompt"] == SCHEDULE_PROMPT
                if scheduled:
                    assert any(source["text"] == UPDATED_DECISION for source in request["sources"])
                output = {
                    "title": "Weekly Planner release brief"
                    if scheduled
                    else "Planner v2.1 release brief",
                    "language": "en",
                    "summary": statement(RELEASE, "S1", RELEASE),
                    "highlights": [],
                    "upgrade_notes": [statement(README, "S2", README)],
                    "open_questions": [],
                }
            else:
                assert request["project"]["instructions"] == "Use product terminology."
                assert any(source["text"] == DECISION for source in request["sources"])
                title = (
                    "Revised monthly export specification"
                    if request.get("prior")
                    else "Monthly export specification"
                )
                output = {
                    "title": title,
                    "language": "en",
                    "requirements": [
                        {
                            **statement(INTERVIEW, "S1", INTERVIEW),
                            "acceptance": ["Verify totals in the export."],
                        },
                        {
                            **statement(DOC, "S2", DOC),
                            "acceptance": ["Check the reporting period."],
                        },
                    ],
                    "assumptions": [],
                    "open_questions": [],
                }
            return AIMessage(content=json.dumps(output))

    class ChatModel(BaseChatModel):
        @property
        def _llm_type(self):
            return "project-browser-fixture"

        def bind_tools(self, _tools, **_kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            context = next(
                json.loads(message.content.split("\n", 1)[1])
                for message in messages
                if isinstance(message, HumanMessage)
                and isinstance(message.content, str)
                and message.content.startswith("Project context for the current request.")
            )
            chat_contexts.append(context)
            assert any(file["text"] == INTERVIEW for file in context["files"])
            specification = next(
                item for item in context["deliverables"] if "export specification" in item["title"]
            )
            reply = (
                f"{context['decisions']} See [{specification['title']}]({specification['url']})."
            )
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=reply))])

    def github(request):
        github_calls.append((request.method, request.url.path, request.url.params.get("ref")))
        assert request.url.host == "api.github.com" and request.method == "GET"
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(
                200, json={"name": "Planner 2.1", "tag_name": "v2.1", "body": RELEASE}
            )
        assert request.url.path == "/repos/acme/planner/readme"
        return httpx.Response(
            200,
            json={
                "encoding": "base64",
                "path": "README.md",
                "content": b64encode(README.encode()).decode(),
            },
        )

    monkeypatch.setattr(
        project_workflows, "create_chat_model", lambda *_args, **_kwargs: WorkflowModel()
    )
    monkeypatch.setattr(
        project_workflows,
        "AsyncClient",
        lambda **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(github), **kwargs),
    )
    monkeypatch.setattr(agent_factory, "_build_llm", lambda *_args, **_kwargs: ChatModel())

    with psycopg.connect(dsn, autocommit=True) as db:
        db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        server = uvicorn.Server(
            uvicorn.Config(main.app, host="127.0.0.1", port=0, log_level="warning")
        )

        def serve():
            with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                runner.run(server.serve())

        backend = Thread(target=serve, daemon=True)
        backend.start()
        try:
            ready = Event()
            for _ in range(100):
                if server.started:
                    break
                assert backend.is_alive()
                ready.wait(0.1)
            assert server.started
            backend_url = f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"

            def make_schedule_due(workspace_id):
                result = db.execute(
                    sql.SQL(
                        "UPDATE {}.weaver_project_schedules SET next_run_at=statement_timestamp() WHERE workspace_id=%s"
                    ).format(sql.Identifier(schema)),
                    (workspace_id,),
                )
                assert result.rowcount == 1

            verify_in_browser(
                backend_url, tmp_path, draft_started, release_draft, make_schedule_due
            )
            assert len(workflow_requests) == 4
            assert workflow_requests[2]["prior"]["title"] == "Monthly export specification"
            assert len(chat_contexts) == 2
            assert (
                github_calls
                == [
                    ("GET", "/repos/acme/planner/releases/latest", None),
                    ("GET", "/repos/acme/planner/readme", "refs/tags/v2.1"),
                ]
                * 2
            )
        finally:
            release_draft.set()
            server.should_exit = True
            backend.join(15)
            assert not backend.is_alive()
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def verify_in_browser(backend_url, tmp_path, draft_started, release_draft, make_schedule_due):
    port = free_port()
    origin = f"http://127.0.0.1:{port}"
    log_path = tmp_path / "next.log"
    with log_path.open("w", encoding="utf-8") as log:
        app = subprocess.Popen(
            [
                "node",
                "node_modules/next/dist/bin/next",
                "start",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=WEB,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    try:
        wait_until_listening(app, port, log_path)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel=os.getenv("WEAVER_E2E_BROWSER_CHANNEL"))
            with browser.new_context() as context:
                context.tracing.start(screenshots=True, snapshots=True)

                def route_api(route):
                    url = urlsplit(route.request.url)
                    if url.path.startswith("/api/"):
                        target = url._replace(netloc=urlsplit(backend_url).netloc)
                        route.continue_(
                            url=target.geturl(), headers={**route.request.headers, **AUTH}
                        )
                    else:
                        route.continue_()

                context.route("**/api/**", route_api)
                context.route_web_socket("**/api/browser/**", lambda socket: socket.close())
                try:
                    page = context.new_page()
                    page.goto(origin + "/workspace")
                    drive_workflows(page, draft_started, release_draft)
                    workspace_id = page.evaluate("localStorage.getItem('weaver-workspace-id')")
                    drive_project_chat(page)
                    page.goto(origin + "/workspace")
                    drive_schedule(page, lambda: make_schedule_due(workspace_id))
                    with httpx.Client(
                        base_url=backend_url, headers=AUTH, trust_env=False
                    ) as client:
                        prefix = f"/api/workspaces/{workspace_id}"
                        artifacts = client.get(prefix + "/deliverables").json()
                        assert len(artifacts) == 4
                        outside = client.get(
                            prefix + "/deliverables", headers={**AUTH, "X-Weaver-User": "bob"}
                        )
                        assert outside.status_code == 404
                except Exception:
                    trace = WEB / "test-results" / "project-runtime.zip"
                    trace.parent.mkdir(exist_ok=True)
                    context.tracing.stop(path=trace)
                    raise
                else:
                    context.tracing.stop()
    finally:
        stop_app(app)


def drive_workflows(page, draft_started, release_draft):
    page.get_by_role("button", name="Create workspace", exact=True).click()
    page.get_by_role("button", name="Edit project", exact=True).click()
    page.get_by_label("Project name", exact=True).fill("Operations")
    page.get_by_label("Project instructions", exact=True).fill("Use product terminology.")
    page.get_by_label("Project decisions", exact=True).fill(DECISION)
    page.get_by_role("button", name="Save project", exact=True).click()
    expect(page.get_by_role("heading", name="Operations", exact=True)).to_be_visible()

    upload = page.get_by_label("Add project file", exact=True)
    for name, content in (("interviews.md", INTERVIEW), ("product.md", DOC)):
        upload.set_input_files(
            {"name": name, "mimeType": "text/markdown", "buffer": content.encode()}
        )
        expect(page.get_by_role("link", name=name, exact=True)).to_be_visible()
    page.get_by_text("Source files · Recent documents", exact=True).click()
    page.get_by_role("checkbox", name="interviews.md", exact=True).check()
    page.get_by_role("checkbox", name="product.md", exact=True).check()
    page.get_by_label("Task prompt", exact=True).fill("Draft the monthly export spec.")
    page.get_by_role("button", name="Run task", exact=True).click()
    drafting = page.get_by_text("Drafting the deliverable and checking citations.", exact=True)
    expect(drafting).to_be_visible(timeout=10_000)
    assert draft_started.wait(10)
    page.reload(wait_until="domcontentloaded")
    expect(drafting).to_be_visible(timeout=10_000)
    release_draft.set()
    expect(
        page.get_by_role("heading", name="Monthly export specification", exact=True)
    ).to_be_visible(timeout=15_000)
    sources = page.get_by_role("region", name="Sources", exact=True)
    expect(sources.get_by_role("link", name="interviews.md", exact=True)).to_have_attribute(
        "href", re.compile(r"/api/workspaces/[0-9a-f]{32}/files/[0-9a-f]{32}$")
    )
    expect(sources.get_by_role("link", name="product.md", exact=True)).to_be_visible()
    with page.expect_download() as download:
        page.get_by_role("link", name="Download Markdown", exact=True).click()
    assert INTERVIEW in download.value.path().read_text(encoding="utf-8")

    page.get_by_label("Workflow", exact=True).select_option("release-brief")
    page.get_by_label("GitHub repository", exact=True).fill("acme/planner")
    page.get_by_label("Task prompt", exact=True).fill("What does the latest release change?")
    page.get_by_role("button", name="Run task", exact=True).click()
    expect(
        page.get_by_role("heading", name="Planner v2.1 release brief", exact=True)
    ).to_be_visible(timeout=15_000)
    expect(
        sources.get_by_role("link", name="acme/planner · Planner 2.1", exact=True)
    ).to_have_attribute("href", "https://github.com/acme/planner/releases/tag/v2.1")
    expect(sources.get_by_text(README, exact=True)).to_be_visible()

    page.get_by_role("button", name="Draft the monthly export spec.", exact=False).click()
    page.get_by_role("button", name="Revise", exact=True).click()
    page.get_by_label("Task prompt", exact=True).fill("Tighten the acceptance criteria.")
    page.get_by_role("button", name="Run task", exact=True).click()
    expect(
        page.get_by_role("heading", name="Revised monthly export specification", exact=True)
    ).to_be_visible(timeout=15_000)
    expect(
        page.get_by_role("button", name="Monthly export specification", exact=True)
    ).to_be_visible()


def drive_project_chat(page):
    page.get_by_role("link", name="Chat in project", exact=True).click()
    expect(page.get_by_role("button", name="Agent", exact=True)).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(page.get_by_text("No recent chats", exact=True)).to_be_visible()
    transcript = page.get_by_test_id("virtuoso-item-list")
    for prompt in ("Summarize the project decision.", "Which previous spec can I use?"):
        chat = page.get_by_role("textbox", name="Ask anything...")
        chat.fill(prompt)
        chat.press("Enter")
        expect(page.get_by_role("status", name="Run status")).to_have_text(
            "Completed", timeout=30_000
        )
        expect(transcript.get_by_text(DECISION, exact=False)).to_be_visible()
        expect(
            transcript.get_by_role("link", name="Revised monthly export specification", exact=True)
        ).to_be_visible()
        if prompt.startswith("Summarize"):
            page.get_by_role("button", name="New Investigation", exact=True).click()


def drive_schedule(page, make_due):
    page.get_by_label("Workflow", exact=True).select_option("release-brief")
    page.get_by_label("GitHub repository", exact=True).fill("acme/planner")
    page.get_by_label("Task prompt", exact=True).fill(SCHEDULE_PROMPT)
    page.get_by_label("Repeat", exact=True).select_option(label="Every 7 days")
    first_run = page.evaluate("""() => {
        const future = new Date(Date.now() + 60 * 60 * 1000);
        return new Date(future.getTime() - future.getTimezoneOffset() * 60000)
          .toISOString().slice(0, 16);
    }""")
    page.get_by_label("First run (local time)", exact=True).fill(first_run)
    page.get_by_role("button", name="Schedule task", exact=True).click()
    schedule = page.get_by_role("region", name="Scheduled tasks")
    expect(schedule.get_by_text(SCHEDULE_PROMPT, exact=True)).to_be_visible()
    schedule.get_by_role("button", name="Pause", exact=True).click()
    expect(schedule.get_by_text("Paused", exact=True)).to_be_visible()

    page.reload(wait_until="domcontentloaded")
    expect(schedule.get_by_text("Paused", exact=True)).to_be_visible()
    page.get_by_role("button", name="Edit project", exact=True).click()
    page.get_by_label("Project decisions", exact=True).fill(UPDATED_DECISION)
    page.get_by_role("button", name="Save project", exact=True).click()
    expect(page.get_by_role("definition").filter(has_text=UPDATED_DECISION)).to_be_visible()
    schedule.get_by_role("button", name="Resume", exact=True).click()
    expect(schedule.get_by_text("Next run", exact=False)).to_be_visible()

    make_due()
    latest = schedule.get_by_role("button", name="View latest run", exact=True)
    expect(latest).to_be_visible(timeout=20_000)
    latest.click()
    result = page.get_by_role("heading", name="Weekly Planner release brief", exact=True)
    expect(result).to_be_visible(timeout=15_000)
    with page.expect_download() as download:
        page.get_by_role("link", name="Download Markdown", exact=True).click()
    assert RELEASE in download.value.path().read_text(encoding="utf-8")
    schedule.get_by_role("button", name="Delete schedule", exact=True).click()
    expect(schedule).to_have_count(0)
    expect(result).to_be_visible()
