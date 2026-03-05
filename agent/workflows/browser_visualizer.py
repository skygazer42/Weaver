"""
Browser visualization helpers for DeepSearch / Tree research.

Goal:
- When running DeepSearch, keep the sandbox browser "alive" (navigate/scroll/screenshot)
  so the frontend Live view is not stuck on a blank page.
- Emit the same tool_* events as sb_browser_* tools so the Thinking accordion and
  screenshot timeline stay consistent.

This module is intentionally best-effort: failures must never break research.
"""

from __future__ import annotations

import logging
import threading
import time
from urllib.parse import urlparse
from typing import Any, Dict, Iterable, List, Optional

from common.config import settings

logger = logging.getLogger(__name__)


_VISITED_LOCK = threading.Lock()
_VISITED_URLS: Dict[str, set[str]] = {}
_VISUALIZE_LOCK = threading.Lock()
_VISUALIZE_IN_FLIGHT: set[str] = set()
_LAST_VISUALIZE_AT: Dict[str, float] = {}


def _resolve_thread_id(state: Dict[str, Any], config: Dict[str, Any]) -> str:
    cfg = config.get("configurable") if isinstance(config, dict) else {}
    thread_id = ""
    if isinstance(cfg, dict):
        thread_id = str(cfg.get("thread_id") or "").strip()
    if not thread_id:
        thread_id = str(state.get("thread_id") or "").strip()
    if not thread_id:
        # Best-effort fallback used elsewhere in deepsearch for the emitter.
        thread_id = str(state.get("cancel_token_id") or "").strip()
    return thread_id


def _can_visualize() -> bool:
    return bool(getattr(settings, "deepsearch_visualize_browser", False))


def _is_http_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return u.startswith("http://") or u.startswith("https://")


def _mark_visited(thread_id: str, url: str) -> bool:
    """
    Mark url as visited for this thread_id.

    Returns True if this is the first time we see it, else False.
    """
    tid = (thread_id or "").strip() or "default"
    u = (url or "").strip()
    if not u:
        return False
    with _VISITED_LOCK:
        seen = _VISITED_URLS.setdefault(tid, set())
        if u in seen:
            return False
        seen.add(u)
        # Safety valve: keep memory bounded.
        if len(seen) > 500:
            # Prefer keeping recent-ish entries (unordered set; best-effort).
            _VISITED_URLS[tid] = set(list(seen)[-300:])
        return True


def _try_begin_visualize(thread_id: str) -> bool:
    tid = (thread_id or "").strip() or "default"
    now = time.time()
    with _VISUALIZE_LOCK:
        if tid in _VISUALIZE_IN_FLIGHT:
            return False
        # Soft throttle to avoid spamming the sandbox/browser thread.
        last = float(_LAST_VISUALIZE_AT.get(tid) or 0.0)
        if (now - last) < 1.5:
            return False
        _VISUALIZE_IN_FLIGHT.add(tid)
        _LAST_VISUALIZE_AT[tid] = now
        return True


def _end_visualize(thread_id: str) -> None:
    tid = (thread_id or "").strip() or "default"
    with _VISUALIZE_LOCK:
        _VISUALIZE_IN_FLIGHT.discard(tid)


def _should_skip_url(url: str) -> bool:
    """
    Avoid previewing very heavy / video-centric sites in the live browser.

    These frequently hang on headless Chromium, slow down the Playwright thread,
    and don't add much value compared to text/article sources.
    """
    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:
        host = ""
    if not host:
        return False
    blocked = (
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
        "bilibili.com",
        "www.bilibili.com",
        "tiktok.com",
        "www.tiktok.com",
        "douyin.com",
        "www.douyin.com",
    )
    return host in blocked


def show_browser_status_page(
    *,
    state: Dict[str, Any],
    config: Dict[str, Any],
    title: str,
    detail: str = "",
) -> None:
    """
    Render a lightweight animated status page in the sandbox browser.

    Purpose: avoid the Live viewer sitting on a blank `about:blank` page while
    the backend is doing slow, blocking work (API search, LLM calls, etc.).
    """
    if bool(state.get("is_cancelled")):
        return
    if not _can_visualize():
        return

    thread_id = _resolve_thread_id(state, config)
    if not thread_id:
        return

    try:
        from tools.sandbox.sandbox_browser_session import sandbox_browser_sessions
    except Exception:
        return

    safe_title = (title or "").strip()[:120]
    safe_detail = (detail or "").strip()[:240]

    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Weaver</title>
    <style>
      :root {{
        color-scheme: light;
      }}
      body {{
        margin: 0;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji";
        background: radial-gradient(80% 120% at 10% 10%, #f5f5f4 0%, #ffffff 55%, #fafaf9 100%);
        color: #1c1917;
      }}
      .wrap {{
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 32px;
      }}
      .card {{
        width: min(720px, 92vw);
        background: rgba(255, 255, 255, 0.82);
        border: 1px solid rgba(0, 0, 0, 0.06);
        border-radius: 16px;
        box-shadow: 0 18px 60px rgba(0, 0, 0, 0.08);
        padding: 18px 18px 16px 18px;
      }}
      .row {{
        display: flex;
        align-items: center;
        gap: 12px;
      }}
      .spinner {{
        width: 18px;
        height: 18px;
        border-radius: 999px;
        border: 2px solid rgba(0,0,0,0.12);
        border-top-color: rgba(16,185,129,0.9);
        animation: spin 0.9s linear infinite;
      }}
      @keyframes spin {{
        to {{ transform: rotate(360deg); }}
      }}
      .title {{
        font-size: 14px;
        font-weight: 600;
        letter-spacing: 0.2px;
      }}
      .detail {{
        margin-top: 8px;
        font-size: 12px;
        color: rgba(41, 37, 36, 0.70);
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        white-space: pre-wrap;
        word-break: break-word;
      }}
      .bar {{
        margin-top: 12px;
        height: 6px;
        width: 100%;
        background: rgba(0,0,0,0.06);
        border-radius: 999px;
        overflow: hidden;
      }}
      .bar > div {{
        height: 100%;
        width: 45%;
        background: linear-gradient(90deg, rgba(16,185,129,0.25), rgba(16,185,129,0.9));
        animation: slide 1.4s ease-in-out infinite;
        border-radius: 999px;
      }}
      @keyframes slide {{
        0% {{ transform: translateX(-20%); opacity: 0.5; }}
        50% {{ transform: translateX(90%); opacity: 1; }}
        100% {{ transform: translateX(220%); opacity: 0.5; }}
      }}
      .hint {{
        margin-top: 10px;
        font-size: 11px;
        color: rgba(41, 37, 36, 0.55);
      }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="card">
        <div class="row">
          <div class="spinner" aria-hidden="true"></div>
          <div class="title">{safe_title or "Working…"}</div>
        </div>
        {"<div class='detail'>" + safe_detail + "</div>" if safe_detail else ""}
        <div class="bar"><div></div></div>
        <div class="hint">Weaver sandbox browser · live preview</div>
      </div>
    </div>
  </body>
</html>
"""

    def _impl() -> None:
        session = sandbox_browser_sessions.get(thread_id)
        page = session.get_page()
        # Avoid overriding a real page; only replace `about:blank`-like states.
        try:
            current_url = str(getattr(page, "url", "") or "").strip().lower()
        except Exception:
            current_url = ""
        if current_url.startswith("http://") or current_url.startswith("https://"):
            return
        page.set_content(html)

    try:
        sandbox_browser_sessions.run_sync(thread_id, _impl)
    except Exception:
        # Status page is best-effort only.
        return


def visualize_urls_from_results(
    *,
    state: Dict[str, Any],
    config: Dict[str, Any],
    results: List[Dict[str, Any]],
    max_urls: int,
    reason: str,
) -> None:
    urls: List[str] = []
    for r in results or []:
        if not isinstance(r, dict):
            continue
        url = str(r.get("url") or "").strip()
        if url:
            urls.append(url)
    visualize_urls(state=state, config=config, urls=urls, max_urls=max_urls, reason=reason)


def visualize_urls(
    *,
    state: Dict[str, Any],
    config: Dict[str, Any],
    urls: Iterable[str],
    max_urls: int,
    reason: str,
) -> None:
    """
    Best-effort navigate/scroll/screenshot for a few URLs.

    This is used purely for UX visualization. It must never raise.
    """
    if bool(state.get("is_cancelled")):
        return
    if not _can_visualize():
        return

    thread_id = _resolve_thread_id(state, config)
    if not thread_id:
        return
    if not _try_begin_visualize(thread_id):
        return

    try:
        # Avoid importing heavy deps unless the feature is enabled + has thread_id.
        try:
            from agent.workflows.source_url_utils import canonicalize_source_url
            from tools.sandbox.sandbox_browser_tools import (
                SbBrowserNavigateTool,
                SbBrowserScrollTool,
            )
        except Exception as e:
            logger.debug(f"[browser_visualizer] import failed: {e}")
            return

        try:
            max_urls = max(0, int(max_urls or 0))
        except Exception:
            max_urls = 0
        if max_urls <= 0:
            return

        navigate = SbBrowserNavigateTool(thread_id=thread_id, emit_events=True, save_screenshots=True)
        scroll = SbBrowserScrollTool(thread_id=thread_id, emit_events=True, save_screenshots=True)

        visited_now = 0
        for raw in urls:
            if visited_now >= max_urls:
                break

            url = canonicalize_source_url(raw)
            if not url or not _is_http_url(url):
                continue
            if _should_skip_url(url):
                continue
            if not _mark_visited(thread_id, url):
                continue

            visited_now += 1
            try:
                logger.info(f"[browser_visualizer] ({reason}) preview: {url}")
                nav_res = navigate._run(
                    url=url,
                    wait_until="domcontentloaded",
                    wait_ms=450,
                    full_page=False,
                )
                if isinstance(nav_res, dict) and nav_res.get("error"):
                    continue

                # Scroll a bit to make it feel like a human skim (and trigger at least one screenshot).
                # Keep amounts moderate to avoid excessive screenshots/log spam.
                scroll._run(amount=520, wait_ms=350, full_page=False)
            except Exception as e:
                logger.debug(f"[browser_visualizer] preview failed: {e}")
                continue
    finally:
        _end_visualize(thread_id)
