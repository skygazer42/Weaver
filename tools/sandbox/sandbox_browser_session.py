from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse

from common.config import settings


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


def _require_e2b() -> None:
    if not settings.e2b_api_key:
        raise RuntimeError("E2B_API_KEY is required for sandbox browser tools.")


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
  else
    echo "No Chrome/Chromium binary found" >&2
    exit 1
  fi
fi
nohup "$CHROME_BIN" \\
  --no-sandbox \\
  --disable-dev-shm-usage \\
  --remote-debugging-port={port} \\
  --remote-debugging-address=0.0.0.0 \\
  --headless=new \\
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

            sandbox = Sandbox(
                template=template,
                timeout=timeout,
                api_key=settings.e2b_api_key,
                domain=domain,
                metadata=metadata,
                allow_internet_access=_bool_env("SANDBOX_ALLOW_INTERNET", True),
            )

            # Ensure chrome is running with remote debugging.
            check = sandbox.commands.run(f"pgrep -f 'remote-debugging-port={port}' || echo not_running")
            if "not_running" in (getattr(check, "stdout", "") or ""):
                sandbox.commands.run(_chrome_start_cmd(port), timeout=60)
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
            for _ in range(12):
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
        self._sessions: Dict[str, SandboxBrowserSession] = {}

    def get(self, thread_id: str) -> SandboxBrowserSession:
        thread_id = (thread_id or "").strip() or "default"
        with self._lock:
            if thread_id not in self._sessions:
                self._sessions[thread_id] = SandboxBrowserSession(thread_id)
            return self._sessions[thread_id]

    def reset(self, thread_id: str) -> None:
        thread_id = (thread_id or "").strip() or "default"
        with self._lock:
            session = self._sessions.pop(thread_id, None)
        if session:
            session.close()


sandbox_browser_sessions = SandboxBrowserSessionManager()
