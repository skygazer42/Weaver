"""
Real (non-mocked) backend API smoke test.

What this does:
- Starts a real `uvicorn` server (separate process) and hits backend endpoints via HTTP.
- Avoids ASGITransport / TestClient (no in-process mocking).
- Runs the server in an isolated temp working directory so side-effects (data/, screenshots/, logs/)
  don't touch the repo checkout.

Typical usage:
    python scripts/live_api_smoke.py

If you want to point at an already running server:
    python scripts/live_api_smoke.py --no-start --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import socket
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx


@dataclass(frozen=True)
class SmokeResult:
    method: str
    path: str
    url: str
    status_code: Optional[int]
    ok: bool
    elapsed_ms: int
    note: str = ""
    body_snippet: str = ""


# These are populated at runtime (after the server is up) by calling status endpoints.
_SERVICE_FLAGS: Dict[str, bool] = {"asr_enabled": True, "tts_enabled": True}
_REQ_SEQ = 0


def _next_test_ip() -> str:
    """
    Provide a deterministic, non-routable test IP for X-Forwarded-For.

    The server's in-memory rate limiter buckets by client IP. A full OpenAPI sweep
    can exceed 60 req/min and slow the run down due to 429 retries. Rotating a
    TEST-NET IP keeps the run fast while still exercising real handlers.
    """
    global _REQ_SEQ
    _REQ_SEQ += 1
    last_octet = ((_REQ_SEQ - 1) % 250) + 1
    return f"203.0.113.{last_octet}"


def _default_headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if extra:
        headers.update({str(k): str(v) for k, v in extra.items() if v is not None})
    headers.setdefault("X-Forwarded-For", _next_test_ip())
    return headers


def _expected_503_note(path: str, status_code: Optional[int]) -> Optional[str]:
    if status_code != 503:
        return None
    if path in {"/api/asr/recognize", "/api/asr/upload"} and not _SERVICE_FLAGS.get(
        "asr_enabled", True
    ):
        return "expected 503 (ASR disabled)"
    if path == "/api/tts/synthesize" and not _SERVICE_FLAGS.get("tts_enabled", True):
        return "expected 503 (TTS disabled)"
    return None


def _retry_after_seconds(resp: httpx.Response) -> float:
    raw = (resp.headers.get("Retry-After") or "").strip()
    if raw:
        try:
            return max(1.0, float(raw))
        except ValueError:
            pass
    try:
        data = resp.json()
        ra = data.get("retry_after") if isinstance(data, dict) else None
        if isinstance(ra, (int, float)):
            return max(1.0, float(ra))
    except Exception:
        pass
    return 1.0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _find_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def _env_for_server(*, tmp_root: Path) -> Dict[str, str]:
    env = dict(os.environ)

    # Avoid proxy leakage into the backend subprocess.
    #
    # Many local environments have `HTTP(S)_PROXY`/`ALL_PROXY` pointing at a
    # SOCKS proxy (e.g. Clash). Some SDKs used by the backend (LLM gateways,
    # E2B sandbox, etc.) may not handle these values reliably, which can make
    # "real" smoke tests flaky or fail with confusing network errors.
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    ):
        env.pop(key, None)

    # Keep server side-effects inside tmp_root
    env["WEAVER_DATA_DIR"] = str(tmp_root / "data")

    # Ensure we can import `main:app` even though cwd is temp.
    repo = str(_repo_root())
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = repo if not existing else f"{repo}{os.pathsep}{existing}"

    # Make logs + subprocess output easier to follow.
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


async def _start_uvicorn(
    *,
    host: str,
    port: int,
    tmp_root: Path,
    log_level: str,
) -> Tuple[asyncio.subprocess.Process, Path, Any]:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        log_level,
        "--no-access-log",
    ]
    log_path = tmp_root / "uvicorn.log"
    log_fh = log_path.open("wb")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(tmp_root),
            env=_env_for_server(tmp_root=tmp_root),
            stdout=log_fh,
            stderr=log_fh,
        )
    except Exception:
        log_fh.close()
        raise
    return proc, log_path, log_fh


async def _stop_process(proc: asyncio.subprocess.Process, *, timeout_s: float = 10.0) -> None:
    if proc.returncode is not None:
        return
    try:
        proc.send_signal(signal.SIGINT)
    except ProcessLookupError:
        return

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout_s)
        return
    except asyncio.TimeoutError:
        pass

    try:
        proc.terminate()
    except ProcessLookupError:
        return

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout_s)
        return
    except asyncio.TimeoutError:
        pass

    try:
        proc.kill()
    except ProcessLookupError:
        return
    await proc.wait()


async def _wait_for_health(
    base_url: str,
    *,
    timeout_s: float,
    proc: Optional[asyncio.subprocess.Process] = None,
    expected_openapi_title: str = "Weaver Research Agent API",
) -> None:
    """
    Wait until the started server is ready *and* looks like Weaver.

    Why we validate OpenAPI:
    When binding to a fixed port, it's possible another service is already
    listening on that port and also returns 200 for `/health`. In that case,
    the smoke test would accidentally run against the wrong service.
    """

    deadline = time.monotonic() + timeout_s
    async with httpx.AsyncClient(base_url=base_url, timeout=2.0, trust_env=False) as client:
        last_err: Optional[BaseException] = None
        while time.monotonic() < deadline:
            if proc is not None and proc.returncode is not None:
                raise RuntimeError(
                    f"uvicorn exited early (code={proc.returncode}) before health check succeeded"
                )
            try:
                resp = await client.get("/health")
                if resp.status_code != 200:
                    last_err = RuntimeError(
                        f"/health returned {resp.status_code}: {(resp.text or '')[:200]}"
                    )
                    await asyncio.sleep(0.2)
                    continue

                # Additional identity check to avoid passing when the port is already in use.
                try:
                    openapi = await client.get("/openapi.json")
                    if openapi.status_code != 200:
                        last_err = RuntimeError(
                            f"/openapi.json returned {openapi.status_code}: {(openapi.text or '')[:200]}"
                        )
                        await asyncio.sleep(0.2)
                        continue
                    data = openapi.json()
                    title = (
                        (data.get("info") or {}).get("title")
                        if isinstance(data, dict)
                        else None
                    )
                    if title != expected_openapi_title:
                        last_err = RuntimeError(
                            f"Unexpected OpenAPI title: {title!r} (expected {expected_openapi_title!r})"
                        )
                        await asyncio.sleep(0.2)
                        continue
                except Exception as e:
                    last_err = e
                    await asyncio.sleep(0.2)
                    continue

                return
            except Exception as e:
                last_err = e
            await asyncio.sleep(0.2)
        raise RuntimeError(f"Server did not become healthy within {timeout_s}s: {last_err}")


def _snippet(text: str, limit: int = 240) -> str:
    text = (text or "").replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


async def _raw_request(
    client: httpx.AsyncClient,
    *,
    method: str,
    path: str,
    params: Optional[dict] = None,
    json_body: Any = None,
    files: Any = None,
    headers: Optional[Dict[str, str]] = None,
    timeout_s: float,
) -> Tuple[SmokeResult, Optional[httpx.Response]]:
    url = str(client.base_url)[:-1] + path
    start_total = time.perf_counter()

    last_resp: Optional[httpx.Response] = None
    for attempt in range(3):
        try:
            last_resp = await client.request(
                method,
                path,
                params=params,
                json=json_body,
                files=files,
                headers=_default_headers(headers),
                timeout=timeout_s,
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_total) * 1000)
            return (
                SmokeResult(
                    method=method.upper(),
                    path=path,
                    url=url,
                    status_code=None,
                    ok=False,
                    elapsed_ms=elapsed_ms,
                    note=f"request failed: {type(e).__name__}: {e}",
                ),
                None,
            )

        if last_resp.status_code != 429:
            break

        # Backoff and retry a couple times so we can actually exercise all endpoints.
        if attempt < 2:
            wait_s = _retry_after_seconds(last_resp)
            print(
                f"[smoke] rate limited: {method.upper()} {path} -> sleeping {wait_s:.0f}s then retry",
                file=sys.stderr,
            )
            await asyncio.sleep(wait_s)

    elapsed_ms = int((time.perf_counter() - start_total) * 1000)
    if last_resp is None:
        return (
            SmokeResult(
                method=method.upper(),
                path=path,
                url=url,
                status_code=None,
                ok=False,
                elapsed_ms=elapsed_ms,
                note="request failed: no response",
            ),
            None,
        )

    expected_503 = _expected_503_note(path, last_resp.status_code)
    ok = (last_resp.status_code < 500 and last_resp.status_code != 429) or bool(expected_503)
    note = expected_503 or ("rate limited (429)" if last_resp.status_code == 429 else "")
    body_snip = _snippet(last_resp.text) if not ok else ""
    return (
        SmokeResult(
            method=method.upper(),
            path=path,
            url=url,
            status_code=last_resp.status_code,
            ok=ok,
            elapsed_ms=elapsed_ms,
            note=note,
            body_snippet=body_snip,
        ),
        last_resp,
    )


async def _request_json(
    client: httpx.AsyncClient,
    *,
    method: str,
    path: str,
    params: Optional[dict] = None,
    json_body: Any = None,
    files: Any = None,
    timeout_s: float,
) -> SmokeResult:
    result, _ = await _raw_request(
        client,
        method=method,
        path=path,
        params=params,
        json_body=json_body,
        files=files,
        headers=None,
        timeout_s=timeout_s,
    )
    return result


async def _request_stream(
    client: httpx.AsyncClient,
    *,
    method: str,
    path: str,
    params: Optional[dict] = None,
    json_body: Any = None,
    timeout_s: float,
    first_byte_timeout_s: float = 1.0,
) -> SmokeResult:
    url = str(client.base_url)[:-1] + path
    start_total = time.perf_counter()

    last_status: Optional[int] = None
    last_note = ""
    last_body_snip = ""

    for attempt in range(3):
        try:
            async with client.stream(
                method,
                path,
                params=params,
                json=json_body,
                headers=_default_headers(),
                timeout=httpx.Timeout(timeout_s, connect=min(5.0, timeout_s)),
            ) as resp:
                last_status = resp.status_code

                if resp.status_code == 429 and attempt < 2:
                    wait_s = _retry_after_seconds(resp)
                    print(
                        f"[smoke] rate limited: {method.upper()} {path} -> sleeping {wait_s:.0f}s then retry",
                        file=sys.stderr,
                    )
                    await asyncio.sleep(wait_s)
                    continue

                ok = resp.status_code < 500 and resp.status_code != 429
                note = ""

                # For event streams, it's fine if no event arrives quickly; success is "connects and is 2xx/4xx".
                if ok and resp.status_code < 400:
                    try:
                        aiter = resp.aiter_bytes()
                        first = await asyncio.wait_for(
                            aiter.__anext__(), timeout=first_byte_timeout_s
                        )
                        note = "stream: received first chunk"
                        last_body_snip = _snippet(
                            first.decode("utf-8", errors="replace"), limit=160
                        )
                    except (asyncio.TimeoutError, httpx.ReadTimeout):
                        note = "stream: no chunk within timeout (ok)"
                    except StopAsyncIteration:
                        note = "stream: ended immediately"
                    except Exception as e:
                        note = f"stream read error (after headers): {type(e).__name__}: {e}"
                elif not ok:
                    try:
                        body = await resp.aread()
                        last_body_snip = _snippet(body.decode("utf-8", errors="replace"))
                    except Exception:
                        last_body_snip = ""

                last_note = note or ("rate limited (429)" if resp.status_code == 429 else "")
                elapsed_ms = int((time.perf_counter() - start_total) * 1000)
                return SmokeResult(
                    method=method.upper(),
                    path=path,
                    url=url,
                    status_code=resp.status_code,
                    ok=ok,
                    elapsed_ms=elapsed_ms,
                    note=last_note,
                    body_snippet=last_body_snip if not ok else "",
                )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_total) * 1000)
            return SmokeResult(
                method=method.upper(),
                path=path,
                url=url,
                status_code=None,
                ok=False,
                elapsed_ms=elapsed_ms,
                note=f"stream request failed: {type(e).__name__}: {e}",
            )

    elapsed_ms = int((time.perf_counter() - start_total) * 1000)
    return SmokeResult(
        method=method.upper(),
        path=path,
        url=url,
        status_code=last_status,
        ok=False,
        elapsed_ms=elapsed_ms,
        note=last_note or "stream request failed",
        body_snippet=last_body_snip,
    )


async def _ws_smoke(*, base_url: str, thread_id: str, timeout_s: float) -> SmokeResult:
    # websockets URL: http(s) -> ws(s)
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    path = f"/api/browser/{thread_id}/stream"
    full = ws_url.rstrip("/") + path
    start = time.perf_counter()
    try:
        import websockets

        # Sandbox-backed browser cold starts can exceed the default per-request timeout.
        ws_timeout = max(float(timeout_s or 0), 60.0)

        async with websockets.connect(
            full, open_timeout=ws_timeout, close_timeout=ws_timeout
        ) as ws:
            # Server sends a status message right after accept().
            msg1_raw = await asyncio.wait_for(ws.recv(), timeout=ws_timeout)

            # Mirror the frontend "live mode": start screencast and expect frames.
            await ws.send(
                json.dumps(
                    {
                        "action": "start",
                        "quality": 50,
                        "max_fps": 10,
                    }
                )
            )

            frames: list[float] = []
            got_started = False
            last_msg: str = ""

            deadline = time.monotonic() + ws_timeout
            while time.monotonic() < deadline:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(1.0, deadline - time.monotonic()))
                last_msg = str(raw)
                try:
                    data = json.loads(raw)
                except Exception:
                    continue

                typ = data.get("type")
                if typ == "status":
                    if data.get("message") == "Screencast started":
                        got_started = True
                elif typ == "frame":
                    frames.append(time.perf_counter())
                    # 2 frames is enough to prove continuous streaming (not just a one-off capture).
                    if len(frames) >= 2 and got_started:
                        break
                elif typ == "error":
                    elapsed_ms = int((time.perf_counter() - start) * 1000)
                    return SmokeResult(
                        method="WS",
                        path=path,
                        url=full,
                        status_code=101,
                        ok=False,
                        elapsed_ms=elapsed_ms,
                        note=f"ws error: {_snippet(str(data.get('message') or ''), 160)}",
                        body_snippet=_snippet(last_msg, 200),
                    )

            # Stop streaming to reduce backend load.
            try:
                await ws.send(json.dumps({"action": "stop"}))
            except Exception:
                pass

            elapsed_ms = int((time.perf_counter() - start) * 1000)
            if len(frames) >= 2:
                span = max(1e-6, frames[-1] - frames[0])
                approx_fps = (len(frames) - 1) / span
                return SmokeResult(
                    method="WS",
                    path=path,
                    url=full,
                    status_code=101,
                    ok=True,
                    elapsed_ms=elapsed_ms,
                    note=(
                        "ws stream ok "
                        f"(frames={len(frames)}, approx_fps={approx_fps:.1f}, "
                        f"recv1={_snippet(str(msg1_raw),80)})"
                    ),
                )

            return SmokeResult(
                method="WS",
                path=path,
                url=full,
                status_code=101,
                ok=False,
                elapsed_ms=elapsed_ms,
                note=(
                    "ws stream returned no frames "
                    f"(recv1={_snippet(str(msg1_raw),80)}, last={_snippet(last_msg,80)})"
                ),
            )
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return SmokeResult(
            method="WS",
            path=path,
            url=full,
            status_code=None,
            ok=False,
            elapsed_ms=elapsed_ms,
            note=f"ws failed: {type(e).__name__}: {e}",
        )


async def _scenario_calls(
    client: httpx.AsyncClient,
    *,
    timeout_s: float,
) -> Tuple[List[SmokeResult], Dict[str, str], List[Tuple[str, str]]]:
    """
    Call a few endpoints with valid payloads to exercise deeper paths.

    Returns:
      - list of results
      - ids dict with keys like: agent_id, scheduled_trigger_id, webhook_trigger_id, share_id, thread_id
      - list of (method, openapi-path) pairs already exercised
    """
    results: List[SmokeResult] = []
    ids: Dict[str, str] = {}
    done: set[Tuple[str, str]] = set()

    # Basic health
    res, _ = await _raw_request(client, method="GET", path="/health", timeout_s=timeout_s)
    results.append(res)
    done.add(("GET", "/health"))

    # Optional services status (used to classify expected 503s).
    res, resp = await _raw_request(client, method="GET", path="/api/asr/status", timeout_s=timeout_s)
    results.append(res)
    done.add(("GET", "/api/asr/status"))
    if resp is not None and resp.status_code == 200:
        try:
            data = resp.json()
            _SERVICE_FLAGS["asr_enabled"] = bool(data.get("enabled")) if isinstance(data, dict) else True
        except Exception:
            pass

    res, resp = await _raw_request(client, method="GET", path="/api/tts/status", timeout_s=timeout_s)
    results.append(res)
    done.add(("GET", "/api/tts/status"))
    if resp is not None and resp.status_code == 200:
        try:
            data = resp.json()
            _SERVICE_FLAGS["tts_enabled"] = bool(data.get("enabled")) if isinstance(data, dict) else True
        except Exception:
            pass

    # Agents CRUD
    create_agent, resp = await _raw_request(
        client,
        method="POST",
        path="/api/agents",
        json_body={
            "name": "Smoke Agent",
            "description": "created by scripts/live_api_smoke.py",
            "system_prompt": "You are a smoke test agent.",
        },
        timeout_s=timeout_s,
    )
    results.append(create_agent)
    done.add(("POST", "/api/agents"))
    agent_id = None
    if resp is not None and resp.status_code < 300:
        try:
            agent_id = resp.json().get("id")
        except Exception:
            agent_id = None
    if agent_id:
        ids["agent_id"] = str(agent_id)
        res, _ = await _raw_request(
            client, method="GET", path=f"/api/agents/{agent_id}", timeout_s=timeout_s
        )
        results.append(res)
        done.add(("GET", "/api/agents/{agent_id}"))
        res, _ = await _raw_request(
            client,
            method="PUT",
            path=f"/api/agents/{agent_id}",
            json_body={
                "name": "Smoke Agent Updated",
                "description": "updated by scripts/live_api_smoke.py",
                "system_prompt": "You are a smoke test agent (updated).",
            },
            timeout_s=timeout_s,
        )
        results.append(res)
        done.add(("PUT", "/api/agents/{agent_id}"))
        res, _ = await _raw_request(
            client,
            method="DELETE",
            path=f"/api/agents/{agent_id}",
            timeout_s=timeout_s,
        )
        results.append(res)
        done.add(("DELETE", "/api/agents/{agent_id}"))

    # Triggers: create one scheduled trigger and one webhook trigger, then delete them.
    scheduled, resp = await _raw_request(
        client,
        method="POST",
        path="/api/triggers/scheduled",
        json_body={
            "name": "Smoke Scheduled",
            "description": "created by live_api_smoke",
            "schedule": "* * * * *",
            "agent_id": "default",
            "task": "smoke_task",
            "task_params": {"hello": "world"},
            "run_immediately": False,
            "timezone": "UTC",
        },
        timeout_s=timeout_s,
    )
    results.append(scheduled)
    done.add(("POST", "/api/triggers/scheduled"))
    sched_id = None
    if resp is not None and resp.status_code < 300:
        try:
            sched_id = resp.json().get("trigger_id")
        except Exception:
            sched_id = None
    if sched_id:
        ids["scheduled_trigger_id"] = str(sched_id)
        res, _ = await _raw_request(
            client, method="GET", path=f"/api/triggers/{sched_id}", timeout_s=timeout_s
        )
        results.append(res)
        done.add(("GET", "/api/triggers/{trigger_id}"))
        res, _ = await _raw_request(
            client, method="POST", path=f"/api/triggers/{sched_id}/pause", timeout_s=timeout_s
        )
        results.append(res)
        done.add(("POST", "/api/triggers/{trigger_id}/pause"))
        res, _ = await _raw_request(
            client, method="POST", path=f"/api/triggers/{sched_id}/resume", timeout_s=timeout_s
        )
        results.append(res)
        done.add(("POST", "/api/triggers/{trigger_id}/resume"))
        res, _ = await _raw_request(
            client, method="GET", path=f"/api/triggers/{sched_id}/executions", timeout_s=timeout_s
        )
        results.append(res)
        done.add(("GET", "/api/triggers/{trigger_id}/executions"))
        res, _ = await _raw_request(
            client, method="DELETE", path=f"/api/triggers/{sched_id}", timeout_s=timeout_s
        )
        results.append(res)
        done.add(("DELETE", "/api/triggers/{trigger_id}"))

    webhook, resp = await _raw_request(
        client,
        method="POST",
        path="/api/triggers/webhook",
        json_body={
            "name": "Smoke Webhook",
            "description": "created by live_api_smoke",
            "agent_id": "default",
            "task": "smoke_webhook_task",
            "task_params": {"ping": "pong"},
            "http_methods": ["POST"],
            "require_auth": False,
        },
        timeout_s=timeout_s,
    )
    results.append(webhook)
    done.add(("POST", "/api/triggers/webhook"))
    webhook_id = None
    if resp is not None and resp.status_code < 300:
        try:
            webhook_id = resp.json().get("trigger_id")
        except Exception:
            webhook_id = None
    if webhook_id:
        ids["webhook_trigger_id"] = str(webhook_id)
        res, _ = await _raw_request(
            client,
            method="POST",
            path=f"/api/webhook/{webhook_id}",
            json_body={"hello": "webhook"},
            timeout_s=timeout_s,
        )
        results.append(res)
        done.add(("POST", "/api/webhook/{trigger_id}"))
        res, _ = await _raw_request(
            client, method="DELETE", path=f"/api/triggers/{webhook_id}", timeout_s=timeout_s
        )
        results.append(res)
        done.add(("DELETE", "/api/triggers/{trigger_id}"))

    # Collaboration: share + comments are backed by filesystem, should work without a session.
    thread_id = "smoke_thread"
    ids["thread_id"] = thread_id
    share, resp = await _raw_request(
        client,
        method="POST",
        path=f"/api/sessions/{thread_id}/share",
        json_body={"permissions": "view", "expires_hours": 1},
        timeout_s=timeout_s,
    )
    results.append(share)
    done.add(("POST", "/api/sessions/{thread_id}/share"))
    share_id = None
    if resp is not None and resp.status_code < 300:
        try:
            share_id = resp.json().get("share", {}).get("id")
        except Exception:
            share_id = None
    if share_id:
        ids["share_id"] = str(share_id)
        res, _ = await _raw_request(
            client, method="GET", path=f"/api/share/{share_id}", timeout_s=timeout_s
        )
        results.append(res)
        done.add(("GET", "/api/share/{share_id}"))
        res, _ = await _raw_request(
            client, method="DELETE", path=f"/api/share/{share_id}", timeout_s=timeout_s
        )
        results.append(res)
        done.add(("DELETE", "/api/share/{share_id}"))

    res, _ = await _raw_request(
        client,
        method="POST",
        path=f"/api/sessions/{thread_id}/comments",
        json_body={"content": "smoke comment", "author": "smoke"},
        timeout_s=timeout_s,
    )
    results.append(res)
    done.add(("POST", "/api/sessions/{thread_id}/comments"))
    res, _ = await _raw_request(
        client,
        method="GET",
        path=f"/api/sessions/{thread_id}/comments",
        timeout_s=timeout_s,
    )
    results.append(res)
    done.add(("GET", "/api/sessions/{thread_id}/comments"))

    return results, ids, sorted(done)


async def _sweep_all_routes(
    client: httpx.AsyncClient,
    *,
    timeout_s: float,
    ids: Dict[str, str],
    already_done: Iterable[Tuple[str, str]],
) -> List[SmokeResult]:
    done = set((m.upper(), p) for (m, p) in already_done)

    openapi = await client.get("/openapi.json", timeout=timeout_s)
    openapi.raise_for_status()
    spec = openapi.json()

    paths: Dict[str, Any] = spec.get("paths", {}) if isinstance(spec, dict) else {}
    results: List[SmokeResult] = []

    def pick_id(name: str) -> str:
        return ids.get(name) or f"smoke_{name}"

    for path, item in sorted(paths.items()):
        if not isinstance(item, dict):
            continue
        for method, op in sorted(item.items()):
            if method.lower() not in {"get", "post", "put", "delete", "patch"}:
                continue
            method_u = method.upper()
            key = (method_u, path)
            if key in done:
                continue

            # Replace known path params with stable ids.
            concrete_path = path
            if "{thread_id}" in concrete_path:
                concrete_path = concrete_path.replace("{thread_id}", pick_id("thread_id"))
            if "{agent_id}" in concrete_path:
                concrete_path = concrete_path.replace("{agent_id}", pick_id("agent_id"))
            if "{trigger_id}" in concrete_path:
                trigger_key = (
                    "webhook_trigger_id"
                    if concrete_path.startswith("/api/webhook/")
                    else "scheduled_trigger_id"
                )
                concrete_path = concrete_path.replace("{trigger_id}", pick_id(trigger_key))
            if "{share_id}" in concrete_path:
                concrete_path = concrete_path.replace("{share_id}", pick_id("share_id"))
            if "{version_id}" in concrete_path:
                concrete_path = concrete_path.replace("{version_id}", "version_does_not_exist")
            if "{filename}" in concrete_path:
                concrete_path = concrete_path.replace("{filename}", "missing.png")
            if "{source}" in concrete_path or "{source:path}" in concrete_path:
                concrete_path = concrete_path.replace("{source:path}", "missing.txt").replace(
                    "{source}", "missing.txt"
                )

            # Minimal per-endpoint bodies
            json_body = None
            files = None
            params = None

            if method_u == "POST" and path == "/api/chat":
                json_body = {
                    "messages": [{"role": "user", "content": "Hello, just say hi."}],
                    "stream": False,
                }
            elif method_u == "POST" and path == "/api/chat/sse":
                json_body = {
                    "messages": [{"role": "user", "content": "Hello, just say hi."}],
                    "stream": True,
                }
            elif method_u == "POST" and path == "/api/support/chat":
                json_body = {"message": "Hello support, just say hi.", "stream": False}
            elif method_u == "POST" and path == "/api/asr/recognize":
                json_body = {"audio_data": "AA==", "format": "wav", "sample_rate": 16000}
            elif method_u == "POST" and path == "/api/tts/synthesize":
                json_body = {"text": "Hello", "voice": "longxiaochun"}
            elif method_u == "POST" and path == "/api/asr/upload":
                files = {"file": ("smoke.wav", b"\x00\x00\x00\x00", "audio/wav")}
            elif method_u == "POST" and path == "/api/documents/upload":
                files = {"file": ("smoke.txt", b"hello", "text/plain")}
            elif method_u == "POST" and path == "/api/documents/search":
                params = {"query": "smoke", "n_results": 3}
            elif method_u == "GET" and path == "/api/documents/list":
                params = {"limit": 10}
            elif method_u == "POST" and path == "/api/research":
                # Query param, streaming response.
                params = {"query": "smoke test"}
            elif method_u == "POST" and path == "/api/research/sse":
                json_body = {"query": "smoke test"}
            elif method_u == "GET" and path == "/api/screenshots":
                params = {"limit": 5}
            elif method_u == "POST" and path == "/api/mcp/config":
                json_body = {}
            elif method_u == "POST" and path == "/api/interrupt/resume":
                json_body = {"thread_id": pick_id("thread_id"), "payload": {}}

            # Streaming endpoints
            if path in {"/api/research", "/api/events/{thread_id}", "/api/chat/sse", "/api/research/sse"}:
                first_byte_timeout_s = 1.5
                if path in {"/api/chat/sse", "/api/research/sse"}:
                    # These hit a real model + graph; allow a little more time
                    # for the first SSE frame.
                    first_byte_timeout_s = 10.0
                results.append(
                    await _request_stream(
                        client,
                        method=method_u,
                        path=concrete_path,
                        params=params,
                        json_body=json_body,
                        timeout_s=max(timeout_s, 10.0),
                        first_byte_timeout_s=first_byte_timeout_s,
                    )
                )
                done.add(key)
                continue

            results.append(
                await _request_json(
                    client,
                    method=method_u,
                    path=concrete_path,
                    params=params,
                    json_body=json_body,
                    files=files,
                    timeout_s=max(timeout_s, 10.0) if path in {"/api/chat", "/api/support/chat"} else timeout_s,
                )
            )
            done.add(key)

    return results


def _format_line(r: SmokeResult) -> str:
    code = "—" if r.status_code is None else str(r.status_code)
    status = "OK" if r.ok else "FAIL"
    note = f" | {r.note}" if r.note else ""
    return f"{status:4} {code:3} {r.elapsed_ms:5}ms {r.method:6} {r.path}{note}"


async def run_smoke(
    *,
    base_url: str,
    timeout_s: float,
    include_ws: bool,
) -> List[SmokeResult]:
    results: List[SmokeResult] = []
    async with httpx.AsyncClient(base_url=base_url, trust_env=False) as client:
        # Run a few "deeper" scenario calls first.
        scenario, ids, already_done = await _scenario_calls(client, timeout_s=timeout_s)
        results.extend(scenario)

        thread_id = ids.get("thread_id", "smoke")
        already_done2 = list(already_done)

        # WS check
        if include_ws:
            # Warm up the sandbox browser session first. Live streaming depends on the
            # Playwright+CDP connection being ready, which can take a while on cold starts.
            warm = await _request_json(
                client,
                method="GET",
                path=f"/api/browser/{thread_id}/info",
                timeout_s=max(timeout_s, 180.0),
            )
            results.append(warm)
            already_done2.append(("GET", "/api/browser/{thread_id}/info"))

            results.append(
                await _ws_smoke(
                    base_url=base_url,
                    thread_id=thread_id,
                    timeout_s=timeout_s,
                )
            )

        # Sweep remaining OpenAPI-described endpoints.
        results.extend(
            await _sweep_all_routes(
                client,
                timeout_s=timeout_s,
                ids=ids,
                already_done=already_done2,
            )
        )

    return results


def _write_report(path: Path, results: List[SmokeResult]) -> None:
    payload = [
        {
            "method": r.method,
            "path": r.path,
            "url": r.url,
            "status_code": r.status_code,
            "ok": r.ok,
            "elapsed_ms": r.elapsed_ms,
            "note": r.note,
            "body_snippet": r.body_snippet,
        }
        for r in results
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="", help="Base URL (for --no-start). Example: http://127.0.0.1:8000")
    p.add_argument("--no-start", action="store_true", help="Do not start uvicorn; use --base-url")
    p.add_argument("--host", default="127.0.0.1", help="Host to bind uvicorn (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=0, help="Port to bind uvicorn (0 = auto)")
    p.add_argument("--log-level", default="warning", help="Uvicorn log level (default: warning)")
    p.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout seconds (default: 20)")
    p.add_argument("--ws", action="store_true", help="Also test WebSocket endpoint")
    p.add_argument("--out", default="", help="Write JSON report to this file")
    return p.parse_args(argv)


async def amain(argv: List[str]) -> int:
    args = parse_args(argv)

    if args.no_start and not args.base_url:
        raise SystemExit("--no-start requires --base-url")

    proc: Optional[asyncio.subprocess.Process] = None
    log_fh: Optional[Any] = None
    log_path: Optional[Path] = None
    tmp_ctx: Optional[tempfile.TemporaryDirectory] = None
    base_url = args.base_url.rstrip("/")

    try:
        if not args.no_start:
            port = int(args.port) if int(args.port) > 0 else _find_free_port(args.host)
            tmp_ctx = tempfile.TemporaryDirectory(prefix="weaver-live-smoke-")
            tmp_root = Path(tmp_ctx.name).resolve()
            base_url = f"http://{args.host}:{port}"

            # If the repo has a real `.env` filled out, copy it into the temp cwd so
            # Pydantic's `env_file=".env"` is honored even though we're not running
            # uvicorn from the repo root.
            repo_env = _repo_root() / ".env"
            if repo_env.is_file():
                try:
                    shutil.copy2(repo_env, tmp_root / ".env")
                    print("[smoke] copied repo .env into temp run dir")
                except Exception as e:
                    print(f"[smoke] failed to copy .env: {e}", file=sys.stderr)

            print(f"[smoke] starting uvicorn at {base_url} (cwd={tmp_root})")
            proc, log_path, log_fh = await _start_uvicorn(
                host=args.host,
                port=port,
                tmp_root=tmp_root,
                log_level=args.log_level,
            )
            try:
                await _wait_for_health(base_url, timeout_s=30.0, proc=proc)
            except Exception:
                if log_path and log_path.exists():
                    try:
                        tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                        print("[smoke] uvicorn log tail:")
                        print(tail.rstrip() or "(empty)")
                    except Exception:
                        pass
                raise
            print("[smoke] server healthy")
        else:
            print(f"[smoke] using existing server at {base_url}")

        results = await run_smoke(base_url=base_url, timeout_s=float(args.timeout), include_ws=bool(args.ws))

        # Print summary
        for r in results:
            print(_format_line(r))

        fails = [r for r in results if not r.ok]
        print()
        print(f"[smoke] total={len(results)} ok={len(results)-len(fails)} fail={len(fails)}")

        if args.out:
            out_path = Path(args.out)
            _write_report(out_path, results)
            print(f"[smoke] wrote report: {out_path}")

        if fails:
            print("[smoke] failures:")
            for r in fails[:25]:
                extra = f" | {r.body_snippet}" if r.body_snippet else ""
                print(f"  - {_format_line(r)}{extra}")
            return 1
        return 0
    finally:
        if proc is not None:
            await _stop_process(proc)
        if log_fh is not None:
            try:
                log_fh.close()
            except Exception:
                pass
        if tmp_ctx is not None:
            tmp_ctx.cleanup()


def main() -> None:
    raise SystemExit(asyncio.run(amain(sys.argv[1:])))


if __name__ == "__main__":
    main()
