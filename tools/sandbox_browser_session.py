from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from common.config import settings


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _bool_env(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
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
    template = _env("SANDBOX_TEMPLATE_BROWSER")
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
    raw = _env("SANDBOX_BROWSER_REMOTE_DEBUG_PORT", "9223")
    try:
        return int(raw)
    except Exception:
        return 9223


def _chrome_start_cmd(port: int) -> str:
    # Port must match the one we later expose via sandbox.get_host(port).
    return f"""
nohup /usr/bin/google-chrome \\
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
  --window-size=1920,1080 \\
  > /tmp/chrome.log 2>&1 &
"""


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
            check = sandbox.commands.run(f"pgrep -f 'chrome.*remote-debugging-port={port}' || echo not_running")
            if "not_running" in (getattr(check, "stdout", "") or ""):
                sandbox.commands.run(_chrome_start_cmd(port), timeout=60)
                time.sleep(5)

            # Build CDP endpoint using E2B host mapping.
            debug = bool(getattr(getattr(sandbox, "connection_config", None), "debug", False))
            scheme = "http" if debug else "https"
            host = sandbox.get_host(port)
            cdp_endpoint = f"{scheme}://{host}"

            pw = sync_playwright().start()
            try:
                browser = pw.chromium.connect_over_cdp(cdp_endpoint)
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

