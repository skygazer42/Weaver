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
from typing import Any, Dict, Iterable, List, Optional

from common.config import settings

logger = logging.getLogger(__name__)


_VISITED_LOCK = threading.Lock()
_VISITED_URLS: Dict[str, set[str]] = {}


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
        if not _mark_visited(thread_id, url):
            continue

        visited_now += 1
        try:
            logger.info(f"[browser_visualizer] ({reason}) preview: {url}")
            nav_res = navigate._run(url=url, wait_until="domcontentloaded", wait_ms=900, full_page=False)
            if isinstance(nav_res, dict) and nav_res.get("error"):
                continue

            # Scroll a bit to make it feel like a human skim (and trigger at least one screenshot).
            # Keep amounts moderate to avoid excessive screenshots/log spam.
            scroll._run(amount=420, wait_ms=450, full_page=False)
            scroll._run(amount=420, wait_ms=450, full_page=False)
        except Exception as e:
            logger.debug(f"[browser_visualizer] preview failed: {e}")
            continue
