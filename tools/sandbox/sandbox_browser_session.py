from __future__ import annotations

import asyncio
import functools
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, TypeVar
from urllib.parse import urlparse, urlunparse

from common.config import settings

from common.e2b_env import prepare_e2b_env

_T = TypeVar("_T")


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _bool_env(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw and isinstance(settings.sandbox_allow_internet, bool):
        return settings.sandbox_allow_internet
    if not raw:
        return default
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


_E2B_PLACEHOLDER_KEYS = {
    "e2b_...",  # common placeholder
    # The repo's .env.example ships with a non-working sample key; treat as placeholder.
    "e2b_39ce8c3d299470afd09b42629c436edec32728d8",
}
_E2B_DISABLED_REASON: Optional[str] = None


def _require_e2b() -> None:
    global _E2B_DISABLED_REASON
    if _E2B_DISABLED_REASON:
        raise RuntimeError(_E2B_DISABLED_REASON)

    key = (settings.e2b_api_key or "").strip()
    if not key or key in _E2B_PLACEHOLDER_KEYS:
        raise RuntimeError(
            "E2B_API_KEY is required for sandbox browser tools. "
            "Get one at https://e2b.dev/docs/api-key"
        )


def _sandbox_domain() -> Optional[str]:
    return _env("E2B_DOMAIN") or None


def _browser_template() -> str:
    template = _env("SANDBOX_TEMPLATE_BROWSER") or (settings.sandbox_template_browser or "").strip()
    if not template:
        raise RuntimeError("SANDBOX_TEMPLATE_BROWSER is required for sandbox browser tools.")
    return template


def _sandbox_timeout_seconds() -> int:
    raw = _env("SANDBOX_TIMEOUT_SECONDS", "900")
    try:
        return max(60, int(raw))
    except Exception:
        return 900


def _chrome_port() -> int:
    raw = _env("SANDBOX_BROWSER_REMOTE_DEBUG_PORT", "9222")
    try:
        return int(raw)
    except Exception:
        return 9222


def _chrome_start_cmd(port: int) -> str:
    # Port must match the one we later expose via sandbox.get_host(port).
    return f"""
set -e
CHROME_BIN="${{SANDBOX_CHROME_BIN:-}}"
if [ -z "$CHROME_BIN" ]; then
  if command -v google-chrome >/dev/null 2>&1; then
    CHROME_BIN="$(command -v google-chrome)"
  elif command -v chromium >/dev/null 2>&1; then
    CHROME_BIN="$(command -v chromium)"
  elif command -v chromium-browser >/dev/null 2>&1; then
    CHROME_BIN="$(command -v chromium-browser)"
  fi
fi

# If system Chrome isn't available, use (or install) Playwright Chromium.
if [ -z "$CHROME_BIN" ]; then
  CHROME_BIN="$(ls -1t /home/user/.cache/ms-playwright/chromium-*/chrome-linux/chrome 2>/dev/null | head -n 1 || true)"
fi
if [ -z "$CHROME_BIN" ]; then
  echo "Chromium not found; installing via playwright-core..." >&2
  cd /opt/playwright-server
  npx playwright-core install chromium
  CHROME_BIN="$(ls -1t /home/user/.cache/ms-playwright/chromium-*/chrome-linux/chrome 2>/dev/null | head -n 1 || true)"
fi
if [ -z "$CHROME_BIN" ]; then
  echo "No Chrome/Chromium binary found" >&2
  exit 1
fi
nohup "$CHROME_BIN" \\
  --no-sandbox \\
  --disable-dev-shm-usage \\
  --remote-debugging-port={port} \\
  --remote-debugging-address=0.0.0.0 \\
  --headless \\
  --disable-gpu \\
  --no-first-run \\
  --no-default-browser-check \\
  --disable-background-networking \\
  --disable-default-apps \\
  --disable-extensions \\
  --disable-sync \\
  --disable-translate \\
  --metrics-recording-only \\
  --mute-audio \\
  --no-zygote \\
  --user-data-dir=/tmp/weaver-chrome-{port} \\
  --window-size=1920,1080 \\
  > /tmp/chrome.log 2>&1 &
"""


def _read_cdp_ws_url_from_sandbox(sandbox: Any, port: int) -> Optional[str]:
    """
    Read Chrome's webSocketDebuggerUrl from within the sandbox.

    We prefer doing this inside the sandbox because some E2B host mappings may not
    expose the /json/version endpoint reliably over HTTPS, while the WebSocket
    endpoint works.
    """
    urls = (
        f"http://127.0.0.1:{port}/json/version",
        f"http://localhost:{port}/json/version",
        f"http://0.0.0.0:{port}/json/version",
    )

    def _run(cmd: str) -> str:
        res = sandbox.commands.run(cmd, timeout=15)
        return (getattr(res, "stdout", "") or "").strip()

    stdout = ""
    for url in urls:
        for cmd in (
            f"curl -fsSL {url}",
            f"wget -qO- {url}",
            f"""python3 - <<'PY'
import urllib.request
print(urllib.request.urlopen("{url}", timeout=2).read().decode("utf-8"))
PY""",
            f"""python - <<'PY'
import urllib.request
print(urllib.request.urlopen("{url}", timeout=2).read().decode("utf-8"))
PY""",
            f"""node - <<'JS'
const http = require('http');
http.get("{url}", (res) => {{
  let data = '';
  res.on('data', (c) => data += c);
  res.on('end', () => console.log(data));
}}).on('error', () => process.exit(1));
JS""",
        ):
            try:
                stdout = _run(cmd)
                if stdout:
                    break
            except Exception:
                continue
        if stdout:
            break

    try:
        if not stdout:
            return None
        # Some tools may emit extra newlines; keep JSON segment only.
        if "{" in stdout and "}" in stdout:
            stdout = stdout[stdout.find("{") : stdout.rfind("}") + 1].strip()
        try:
            import json as _json

            data = _json.loads(stdout)
        except Exception:
            return None
        ws_url = (data.get("webSocketDebuggerUrl") or "").strip()
        return ws_url or None
    except Exception:
        return None


@dataclass
class SandboxBrowserHandles:
    sandbox: Any
    cdp_endpoint: str
    playwright: Any
    browser: Any
    context: Any
    page: Any


class SandboxBrowserSession:
    """
    Per-thread sandbox-backed real Chromium session (CDP via Playwright).

    This mirrors the FuFanManus idea:
    - create E2B sandbox with a browser template
    - start Chrome with remote debugging port
    - connect over CDP from the backend process
    """

    def __init__(self, thread_id: str):
        self.thread_id = (thread_id or "").strip() or "default"
        self._lock = threading.Lock()
        self._handles: Optional[SandboxBrowserHandles] = None

    def _ensure_sandbox_and_page(self) -> SandboxBrowserHandles:
        with self._lock:
            if self._handles is not None:
                return self._handles

            _require_e2b()

            try:
                from e2b_code_interpreter import Sandbox  # type: ignore
            except Exception as e:
                raise RuntimeError("Missing dependency: e2b-code-interpreter") from e

            try:
                from playwright.sync_api import sync_playwright  # type: ignore
            except Exception as e:
                raise RuntimeError(
                    "Missing dependency: playwright. Install with `pip install playwright` and run "
                    "`python -m playwright install chromium`."
                ) from e

            template = _browser_template()
            domain = _sandbox_domain()
            timeout = _sandbox_timeout_seconds()
            port = _chrome_port()

            metadata: Dict[str, str] = {
                "weaver": "sandbox_browser",
                "thread_id": self.thread_id,
            }

            prepare_e2b_env(domain)
            try:
                sandbox = Sandbox(
                    template=template,
                    timeout=timeout,
                    api_key=settings.e2b_api_key,
                    domain=domain,
                    metadata=metadata,
                    allow_internet_access=_bool_env("SANDBOX_ALLOW_INTERNET", True),
                )
            except Exception as e:
                # Common failure mode: 401 Invalid API key → avoid repeated API calls.
                msg = str(e)
                if "Invalid API key" in msg or "Cannot get the team" in msg or "401" in msg:
                    global _E2B_DISABLED_REASON
                    _E2B_DISABLED_REASON = (
                        "Invalid E2B_API_KEY for sandbox tools. "
                        "Set a valid key from https://e2b.dev/docs/api-key"
                    )
                    raise RuntimeError(_E2B_DISABLED_REASON) from e
                raise

            # Ensure Chrome/Chromium is running with the remote debugging port.
            # NOTE: pgrep can match itself when the pattern appears in argv, so we
            # filter by browser name after.
            check = sandbox.commands.run(
                "pgrep -af 'remote-debugging-port={port}' | "
                "grep -E '(chrome|chromium)' | "
                "grep -v pgrep || echo not_running".format(port=port)
            )
            if "not_running" in (getattr(check, "stdout", "") or ""):
                sandbox.commands.run(_chrome_start_cmd(port), timeout=600)
                time.sleep(5)

            debug = bool(getattr(getattr(sandbox, "connection_config", None), "debug", False))
            http_scheme = "http" if debug else "https"
            ws_scheme = "ws" if debug else "wss"
            host = sandbox.get_host(port)
            cdp_http_endpoint = f"{http_scheme}://{host}"

            # Prefer connecting via WebSocket (wss://...) using the devtools path
            # discovered inside the sandbox. This avoids relying on /json/version
            # being reachable via the external host mapping.
            cdp_endpoint = cdp_http_endpoint
            ws_debugger_url = None
            for _ in range(60):
                ws_debugger_url = _read_cdp_ws_url_from_sandbox(sandbox, port)
                if ws_debugger_url:
                    break
                time.sleep(1)

            cdp_ws_endpoint = None
            if ws_debugger_url:
                parsed = urlparse(ws_debugger_url)
                cdp_ws_endpoint = urlunparse(
                    (
                        ws_scheme,
                        host,
                        parsed.path,
                        parsed.params,
                        parsed.query,
                        parsed.fragment,
                    )
                )
                cdp_endpoint = cdp_ws_endpoint

            pw = sync_playwright().start()
            try:
                endpoints_to_try = []
                if cdp_ws_endpoint:
                    endpoints_to_try.append(cdp_ws_endpoint)
                    if cdp_ws_endpoint.startswith("wss://"):
                        endpoints_to_try.append("ws://" + cdp_ws_endpoint[len("wss://") :])
                    elif cdp_ws_endpoint.startswith("ws://"):
                        endpoints_to_try.append("wss://" + cdp_ws_endpoint[len("ws://") :])
                else:
                    # Fallback: some providers expose /json/version over HTTP(S).
                    endpoints_to_try.append(cdp_http_endpoint)

                last_exc: Optional[Exception] = None
                browser = None
                for endpoint in endpoints_to_try:
                    try:
                        browser = pw.chromium.connect_over_cdp(endpoint)
                        cdp_endpoint = endpoint
                        break
                    except Exception as e:
                        last_exc = e
                if browser is None:
                    raise last_exc or RuntimeError("Failed to connect to sandbox browser via CDP.")
                context = browser.contexts[0] if getattr(browser, "contexts", None) else browser.new_context()
                page = context.new_page()
            except Exception:
                try:
                    pw.stop()
                except Exception:
                    pass
                try:
                    sandbox.kill()
                except Exception:
                    pass
                raise

            self._handles = SandboxBrowserHandles(
                sandbox=sandbox,
                cdp_endpoint=cdp_endpoint,
                playwright=pw,
                browser=browser,
                context=context,
                page=page,
            )
            return self._handles

    def get_page(self) -> Any:
        return self._ensure_sandbox_and_page().page

    def get_info(self) -> Dict[str, str]:
        h = self._ensure_sandbox_and_page()
        return {
            "cdp_endpoint": h.cdp_endpoint,
        }

    def close(self) -> None:
        with self._lock:
            h = self._handles
            self._handles = None

        if not h:
            return

        try:
            try:
                h.page.close()
            except Exception:
                pass
            try:
                h.context.close()
            except Exception:
                pass
            try:
                h.browser.close()
            except Exception:
                pass
            try:
                h.playwright.stop()
            except Exception:
                pass
        finally:
            try:
                h.sandbox.kill()
            except Exception:
                pass


class SandboxBrowserSessionManager:
    def __init__(self):
        self._lock = threading.Lock()
        # Playwright sync API objects are thread-affine. LangGraph tool execution
        # may run in a thread pool, so we keep a dedicated session per
        # (conversation thread_id, worker thread ident) to avoid cross-thread
        # usage that triggers greenlet errors.
        self._sessions: Dict[tuple[str, int], SandboxBrowserSession] = {}
        # Additionally, provide an opt-in per-thread single-worker executor so
        # async FastAPI endpoints (WebSocket, screenshots) can safely interact
        # with the sync Playwright API without running it on the asyncio loop.
        self._executors: Dict[str, ThreadPoolExecutor] = {}
        self._executor_thread_id: Dict[str, int] = {}

    def _normalize_thread_id(self, thread_id: str) -> str:
        return (thread_id or "").strip() or "default"

    def _key(self, thread_id: str) -> tuple[str, int]:
        thread_id = self._normalize_thread_id(thread_id)
        return (thread_id, threading.get_ident())

    def get(self, thread_id: str) -> SandboxBrowserSession:
        key = self._key(thread_id)
        with self._lock:
            if key not in self._sessions:
                self._sessions[key] = SandboxBrowserSession(key[0])
            return self._sessions[key]

    def _get_executor(self, thread_id: str) -> ThreadPoolExecutor:
        thread_id = self._normalize_thread_id(thread_id)
        with self._lock:
            executor = self._executors.get(thread_id)
            if executor is None:
                executor = ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix=f"weaver-sb-{thread_id[:12]}",
                )
                self._executors[thread_id] = executor
            return executor

    def _run_and_record(self, thread_id: str, fn: Callable[[], _T]) -> _T:
        thread_id = self._normalize_thread_id(thread_id)
        with self._lock:
            self._executor_thread_id[thread_id] = threading.get_ident()
        return fn()

    def run_sync(self, thread_id: str, fn: Callable[..., _T], *args, **kwargs) -> _T:
        """
        Run `fn(*args, **kwargs)` on a per-thread single-worker executor and block for result.

        This is safe to call from any thread and keeps sync Playwright objects
        confined to a single thread per conversation thread_id.
        """
        thread_id = self._normalize_thread_id(thread_id)
        with self._lock:
            executor_thread_id = self._executor_thread_id.get(thread_id)

        if executor_thread_id is not None and threading.get_ident() == executor_thread_id:
            return fn(*args, **kwargs)

        executor = self._get_executor(thread_id)
        bound = functools.partial(fn, *args, **kwargs)
        return executor.submit(self._run_and_record, thread_id, bound).result()

    async def run_async(self, thread_id: str, fn: Callable[..., _T], *args, **kwargs) -> _T:
        """
        Run `fn(*args, **kwargs)` on a per-thread single-worker executor and await result.

        Intended for async FastAPI endpoints to avoid calling sync Playwright APIs
        on the running asyncio event loop.
        """
        thread_id = self._normalize_thread_id(thread_id)
        with self._lock:
            executor_thread_id = self._executor_thread_id.get(thread_id)

        if executor_thread_id is not None and threading.get_ident() == executor_thread_id:
            return fn(*args, **kwargs)

        executor = self._get_executor(thread_id)
        bound = functools.partial(fn, *args, **kwargs)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(executor, functools.partial(self._run_and_record, thread_id, bound))

    def reset(self, thread_id: str) -> None:
        thread_id = self._normalize_thread_id(thread_id)

        # Best-effort: close the primary session on its executor thread to avoid
        # Playwright's "sync API inside asyncio loop"/greenlet thread-affinity errors.
        with self._lock:
            executor = self._executors.get(thread_id)

        if executor is not None:
            try:
                self.run_sync(thread_id, lambda: self.get(thread_id).close())
            except Exception:
                pass

        with self._lock:
            keys = [k for k in list(self._sessions.keys()) if k[0] == thread_id]
            sessions = [self._sessions.pop(k) for k in keys]
            executor = self._executors.pop(thread_id, None)
            self._executor_thread_id.pop(thread_id, None)

        # Close any remaining sessions best-effort (may already be closed).
        for session in sessions:
            try:
                session.close()
            except Exception:
                pass

        if executor is not None:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                executor.shutdown(wait=False)
            except Exception:
                pass


sandbox_browser_sessions = SandboxBrowserSessionManager()
