"""Browser acceptance tests for chat and the resumable SSE contract."""

import json
import os
import socket
import subprocess
import time
import unittest
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Condition, Event, Thread
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

WEB = Path(__file__).resolve().parents[1] / "web"
BOOKMARK = "JUNIPER-472"
TOOL_CALL = {"id": "write-1", "name": "write_note", "args": {"path": "fixture.txt"}}
TOOL = {"name": "lookup_receipt", "toolCallId": "lookup-1", "status": "running"}
ARTIFACT_PATH = "/api/tool-artifacts/fixture-output"
ARTIFACT_CONTENT = "x" * 80_000 + "-tail-marker"


class Run:
    def __init__(self, run_id, request):
        self.id = run_id
        self.thread_id = f"thread_{run_id}"
        self.request = request
        self.events = []
        self.changed = Condition()
        self.closed = False
        self.release_post = Event()
        self.cancelled = Event()
        self.approvals = []
        self.decision_requests = 0
        self.tool_executions = 0
        self.cursors = []

    def emit(self, kind, data, closed=False):
        with self.changed:
            self.events.append((kind, data))
            self.closed = closed
            self.changed.notify_all()

    def finish(self, reply):
        self.emit("text", {"content": reply})
        self.emit("run_status", {"status": "completed"})
        self.emit("done", {}, closed=True)


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Last-Event-ID")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Expose-Headers", "X-Thread-ID")
        super().end_headers()

    def send_json(self, status, payload):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def stream(self, run, cursor):
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("X-Thread-ID", run.thread_id)
            self.end_headers()
            while True:
                with run.changed:
                    run.changed.wait_for(
                        lambda start=cursor: len(run.events) > start or run.closed, timeout=10
                    )
                    events = run.events[cursor:]
                    closed = run.closed
                for kind, data in events:
                    cursor += 1
                    payload = json.dumps({"type": kind, "data": data})
                    self.wfile.write(f"id: {cursor}\nevent: {kind}\ndata: {payload}\n\n".encode())
                    self.wfile.flush()
                if closed or not events:
                    return
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        if self.path == ARTIFACT_PATH:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Disposition", 'attachment; filename="fixture-output.txt"')
            self.end_headers()
            self.wfile.write(ARTIFACT_CONTENT.encode())
            return
        if self.path.startswith("/api/chat/sse/"):
            run = self.server.runs.get(self.path.rsplit("/", 1)[1])
            if run is not None:
                cursor = int(self.headers.get("Last-Event-ID", 0))
                run.cursors.append(cursor)
                # Replay the last text frame once to exercise client-side deduplication.
                if cursor and run.request["messages"][-1]["content"] == "Hold the response":
                    cursor -= 1
                self.stream(run, cursor)
                return
        self.send_json(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        url = urlparse(self.path)
        if url.path == "/api/interrupt/resume":
            run = next(
                (run for run in self.server.runs.values() if run.thread_id == body["thread_id"]),
                None,
            )
            if run is None:
                self.send_json(404, {})
                return
            run.decision_requests += 1
            if run.approvals or body["payload"].get("interrupt_ids") != [f"{run.id}-approval"]:
                self.send_json(409, {})
                return
            approved = body["payload"]["tool_approved"]
            run.approvals.append(approved)
            run.emit("run_status", {"status": "running"})
            run.tool_executions += int(approved)
            run.finish("Tool approved and executed" if approved else "Tool rejected")
            self.send_json(202, {"status": "running", "run_id": run.id, "thread_id": run.thread_id})
            return
        keys = parse_qs(url.query).get("research_id")
        if url.path != "/api/chat/sse" or not keys:
            self.send_json(404, {})
            return
        run = Run(keys[0], body)
        self.server.runs[run.id] = run
        self.server.submissions.append(run)
        self.server.run_started.set()
        prompt = body["messages"][-1]["content"]
        run.emit("run_status", {"status": "queued"})
        run.emit("run_status", {"status": "running"})
        if prompt.startswith("Remember"):
            run.finish("Receipt saved")
        elif prompt.startswith("Which receipt"):
            history = body["messages"][:-1]
            found = any(m["role"] == "user" and BOOKMARK in m["content"] for m in history)
            run.finish(f"The receipt is {BOOKMARK}" if found else "Receipt history was missing")
        elif prompt.startswith("Await approval"):
            run.emit(
                "interrupt",
                {
                    "prompts": [{"message": "Write a local note?", "tool_calls": [TOOL_CALL]}],
                    "interrupt_ids": [f"{run.id}-approval"],
                },
            )
            run.emit("run_status", {"status": "awaiting_approval"}, closed=True)
        elif prompt == "Hold the response":
            run.release_post.wait(timeout=20)
        elif prompt == "Read large result":
            run.emit("tool", {**TOOL, "status": "completed"})
            run.emit(
                "artifact",
                {
                    "id": "fixture-output",
                    "type": "tool_output",
                    "title": "Receipt lookup output",
                    "content": "Receipt preview",
                    "tool_call_id": "lookup-1",
                    "download_url": ARTIFACT_PATH,
                },
            )
            run.finish("Lookup finished")
        elif prompt == "Research the missing evidence":
            run.emit(
                "sources",
                {"items": [{"title": "Search log", "url": "https://example.org/search-log"}]},
            )
            run.emit("run_status", {"status": "insufficient_evidence"})
            run.emit("done", {}, closed=True)
        self.stream(run, 0)

    def do_DELETE(self):
        run = self.server.runs.get(self.path.rsplit("/", 1)[1])
        if run is None:
            self.send_json(404, {})
            return
        run.cancelled.set()
        run.emit("run_status", {"status": "cancelled"})
        run.emit("cancelled", {"message": "Task was cancelled"})
        run.emit("done", {}, closed=True)
        self.send_json(202, {"status": "cancelling"})


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_until_listening(app, port, log):
    deadline = time.monotonic() + 30
    while app.poll() is None and time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"Next.js did not start. See {log}")


def stop_app(app):
    if app.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(app.pid), "/T", "/F"], capture_output=True, check=False
        )
    else:
        app.terminate()
    app.wait(timeout=15)


class ChatBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (WEB / ".next" / "BUILD_ID").is_file():
            raise RuntimeError(
                "Build the frontend with pnpm -C web build before running browser tests."
            )
        fixture = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.fixture = fixture
        thread = Thread(target=fixture.serve_forever, daemon=True)
        thread.start()
        cls.addClassCleanup(fixture.server_close)
        cls.addClassCleanup(fixture.shutdown)
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        cls.browser = cls.playwright.chromium.launch(
            channel=os.environ.get("WEAVER_E2E_BROWSER_CHANNEL")
        )
        cls.addClassCleanup(cls.browser.close)

        port = free_port()
        cls.origin = f"http://127.0.0.1:{port}"
        cls.output = WEB / "test-results"
        cls.output.mkdir(exist_ok=True)
        log_path = cls.output / "next.log"
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
            )
        cls.addClassCleanup(stop_app, app)
        wait_until_listening(app, port, log_path)

    def setUp(self):
        self.fixture.runs = {}
        self.fixture.submissions = deque()
        self.fixture.run_started = Event()
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 900})
        self.addCleanup(self.context.close)
        self.context.route("**/*", self.route_request)
        self.context.route_web_socket("**/api/browser/**", lambda socket: socket.close())
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.addCleanup(self.stop_trace)
        self.page = self.context.new_page()
        self.page.goto(self.origin, wait_until="domcontentloaded")
        expect(self.page.get_by_text("No recent chats", exact=True)).to_be_visible()
        self.input = self.page.get_by_role("textbox", name="Ask anything...")
        self.status = self.page.get_by_role("status", name="Run status")

    def route_request(self, route):
        url = urlparse(route.request.url)
        if url.scheme == "http" and url.path.startswith("/api/"):
            target = url._replace(netloc=f"127.0.0.1:{self.fixture.server_port}")
            route.continue_(url=target.geturl())
        elif route.request.url.startswith(f"{self.origin}/"):
            route.continue_()
        else:
            route.abort()

    def stop_trace(self):
        result = self._outcome.result
        trace = self.output / f"{self._testMethodName}.zip"
        if any(test is self for test, _ in result.errors + result.failures):
            self.context.tracing.stop(path=trace)
            for run in self.fixture.runs.values():
                print(f"{run.id=} {run.thread_id=} cursors={run.cursors} events={len(run.events)}")
            print(f"Browser trace: {trace}")
        else:
            trace.unlink(missing_ok=True)
            self.context.tracing.stop()

    def submit(self, prompt):
        self.input.fill(prompt, timeout=5_000)
        self.input.press("Enter")

    def choose_agent(self):
        agent = self.page.get_by_role("button", name="Agent", exact=True)
        agent.click()
        expect(agent).to_have_attribute("aria-pressed", "true")

    def test_agent_history_survives_reload_and_reopen(self):
        self.choose_agent()
        self.submit(f"Remember receipt {BOOKMARK}")
        expect(self.page.get_by_text("Receipt saved", exact=True)).to_be_visible()
        expect(self.status).to_have_text("Completed")
        self.submit("Which receipt was saved?")
        expect(self.page.get_by_text(f"The receipt is {BOOKMARK}", exact=True)).to_be_visible()
        self.page.reload(wait_until="domcontentloaded")
        self.page.get_by_role("button", name=f"Remember receipt {BOOKMARK}", exact=True).click()
        expect(
            self.page.get_by_role("button", name="Agent", exact=True, pressed=True)
        ).to_be_visible()
        self.submit("Which receipt did I mention first?")
        expect(self.page.get_by_text(f"The receipt is {BOOKMARK}", exact=True).last).to_be_visible()
        expect(self.status).to_have_text("Completed")
        requests = [run.request for run in self.fixture.submissions]
        self.assertEqual(len(requests), 3)
        self.assertTrue(requests[0]["conversation_id"])
        self.assertEqual(
            {request["conversation_id"] for request in requests}, {requests[0]["conversation_id"]}
        )
        self.assertEqual({request["search_mode"] for request in requests}, {"agent"})
        self.assertEqual(len({run.id for run in self.fixture.submissions}), 3)

    def test_reload_before_headers_reopens_tool_run_and_stops_it(self):
        self.choose_agent()
        with self.page.expect_request(
            lambda request: request.method == "POST" and "/api/chat/sse?" in request.url
        ):
            self.submit("Hold the response")
        self.assertTrue(self.fixture.run_started.wait(timeout=5))
        self.page.reload(wait_until="domcontentloaded")
        expect(self.status).to_have_text("Running")
        run = self.fixture.submissions[0]
        self.addCleanup(run.release_post.set)
        run.emit("tool", TOOL)
        run.emit("text", {"content": "Live tool reply"})
        expect(self.page.get_by_text("Live tool reply", exact=True)).to_be_visible()
        self.page.reload(wait_until="domcontentloaded")
        expect(self.page.get_by_text("Live tool reply", exact=True)).to_be_visible()
        run.emit("status", {"text": "Writing report"})
        expect(self.status.locator("..")).to_contain_text("Writing report")
        self.page.get_by_role("button", name="New Investigation").click()
        expect(self.page.get_by_text("Live tool reply", exact=True)).to_have_count(0)
        run.emit("text", {"content": " with report progress"})
        self.assertFalse(run.cancelled.is_set())
        self.page.get_by_role("button", name="Hold the response", exact=True).click()
        expect(
            self.page.get_by_text("Live tool reply with report progress", exact=True)
        ).to_be_visible()
        with self.page.expect_response(
            lambda response: response.request.method == "DELETE"
        ) as stopped:
            self.page.get_by_role("button", name="Stop generating").click()
        self.assertEqual(stopped.value.status, 202)
        expect(self.status).to_have_text("Cancelled")
        self.assertTrue(run.cancelled.is_set())
        self.assertEqual(len(self.fixture.submissions), 1)
        self.assertEqual(run.cursors, [0, 4, 5])
        expect(
            self.page.get_by_text("Live tool reply with report progress", exact=True)
        ).to_have_count(1)

    def test_approval_and_refusal_survive_reload(self):
        self.choose_agent()
        for approved in (True, False):
            with self.subTest(approved=approved):
                self.submit(f"Await approval {'yes' if approved else 'no'}")
                expect(self.status).to_have_text("Awaiting approval")
                self.page.reload(wait_until="domcontentloaded")
                approval = self.page.get_by_role("region", name="Tool approval required")
                expect(approval.get_by_text("write_note", exact=True)).to_be_visible()
                expect(approval.get_by_text('"path": "fixture.txt"', exact=False)).to_be_visible()
                choice = approval.get_by_role(
                    "button", name="Approve & Continue" if approved else "Reject"
                )
                expect(choice).to_be_enabled()
                choice.evaluate("button => {button.click(); button.click()}")
                expect(self.status).to_have_text("Completed")
                expect(
                    self.page.get_by_text(
                        "Tool approved and executed" if approved else "Tool rejected", exact=True
                    )
                ).to_be_visible()
                run = self.fixture.submissions[-1]
                self.assertEqual(run.approvals, [approved])
                self.assertEqual(run.decision_requests, 1)
                self.assertEqual(run.tool_executions, int(approved))
                self.assertEqual(run.cursors, [4, 4])
                expect(approval).to_have_count(0)

    def test_tool_output_preview_downloads_full_result(self):
        self.choose_agent()
        self.submit("Read large result")
        expect(self.status).to_have_text("Completed")
        panel = self.page.get_by_role("region", name="Artifacts", exact=True)
        expect(panel.get_by_text("Receipt preview", exact=True)).to_be_visible()
        with self.page.expect_download() as download:
            panel.get_by_role("link", name="Download Receipt lookup output").click()
        self.assertEqual(download.value.path().read_text(encoding="utf-8"), ARTIFACT_CONTENT)

    def test_insufficient_evidence_is_retryable_and_keeps_sources(self):
        self.page.get_by_role("button", name="Deep Research", exact=True).last.click()
        self.submit("Research the missing evidence")
        expect(self.status).to_have_text("Insufficient evidence")
        expect(self.page.get_by_role("link", name="Search log")).to_be_visible()
        with self.page.expect_response(
            lambda response: response.request.method == "POST" and "/api/chat/sse?" in response.url
        ):
            self.page.get_by_role("button", name="Retry research").click()
        expect(self.status).to_have_text("Insufficient evidence")
        self.assertEqual(len(self.fixture.submissions), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
