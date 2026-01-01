"""
Sandbox Web Search Tool with Visual Search Process.

This module provides web search functionality using sandbox browser:
- Performs searches via Google/Bing/DuckDuckGo
- Parses search result pages
- Returns structured results with screenshots
- Emits events for visualization

Similar to Manus's sandbox_web_search_tool.py but adapted for Weaver.

Usage:
    from tools.sandbox.sandbox_web_search_tool import build_sandbox_web_search_tools

    tools = build_sandbox_web_search_tools(thread_id="thread_123")
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import quote_plus, urljoin

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from common.config import settings
from .sandbox_browser_session import sandbox_browser_sessions

logger = logging.getLogger(__name__)


# Search engine configurations
SEARCH_ENGINES = {
    "google": {
        "url": "https://www.google.com/search?q={query}&hl=zh-CN",
        "result_selector": "div.g",
        "title_selector": "h3",
        "link_selector": "a",
        "snippet_selector": "div[data-sncf], div.VwiC3b",
    },
    "bing": {
        "url": "https://www.bing.com/search?q={query}&setlang=zh-Hans",
        "result_selector": "li.b_algo",
        "title_selector": "h2",
        "link_selector": "a",
        "snippet_selector": "p, .b_caption p",
    },
    "duckduckgo": {
        "url": "https://duckduckgo.com/?q={query}&kl=cn-zh",
        "result_selector": "article[data-testid='result']",
        "title_selector": "h2",
        "link_selector": "a[data-testid='result-title-a']",
        "snippet_selector": "div[data-result='snippet']",
    },
}

_BROWSER_CLOSED_ERROR_FRAGMENTS = (
    "TargetClosedError",
    "Target page, context or browser has been closed",
    "browser has been closed",
    "Browser has been closed",
    "Browser closed",
    "Playwright connection closed",
)


def _looks_like_browser_closed_error(err: Exception) -> bool:
    msg = str(err) or ""
    return any(fragment in msg for fragment in _BROWSER_CLOSED_ERROR_FRAGMENTS)


def _safe_page_text(page, *, max_chars: int = 5000) -> str:
    """Best-effort: read visible page text / HTML for captcha/challenge detection."""
    budget = max(0, int(max_chars or 0))
    if budget <= 0:
        return ""

    parts: List[str] = []
    try:
        text = page.inner_text("body", timeout=2000) or ""
        if text:
            parts.append(text)
    except Exception:
        pass

    # Some interstitials don't expose meaningful innerText quickly; fall back to HTML.
    try:
        html = page.content() or ""
        if html:
            parts.append(html)
    except Exception:
        pass

    joined = "\n".join(parts)
    return joined[:budget]


def _looks_like_antibot_challenge(page, engine_config: Optional[Dict[str, str]] = None) -> bool:
    """
    Heuristic detection for anti-bot interstitials (captcha / "are you human" pages).

    In some sandbox environments, major search engines frequently return challenge pages.
    When detected, we fall back to API-based search to keep the tool usable.
    """
    try:
        url = (getattr(page, "url", "") or "").strip()
    except Exception:
        url = ""
    try:
        title = (page.title() or "").strip()
    except Exception:
        title = ""

    text = _safe_page_text(page, max_chars=8000)
    haystack = f"{url}\n{title}\n{text}".lower()

    patterns = (
        # Generic
        "captcha",
        "verify you are",
        "verification",
        "unusual traffic",
        "are you a human",
        "please complete",
        "please verify",
        "challenge",
        # Chinese
        "验证码",
        "人机",
        "验证",
        "访问异常",
        "请完成",
        "抱歉",
        # DuckDuckGo specific
        "bots use duckduckgo",
        "duckduckgo too",
        "select all squares containing a duck",
        # Google specific
        "/sorry/",
    )
    if any(p in haystack for p in patterns):
        return True

    # Structural heuristic: if the expected result containers never appear, treat as blocked.
    if engine_config:
        sel = (engine_config.get("result_selector") or "").strip()
        if sel:
            try:
                if page.locator(sel).count() <= 0:
                    # Many challenges include a "protected"/"verification" marker.
                    if any(p in haystack for p in ("protected", "verification", "verify", "captcha", "challenge")):
                        return True
            except Exception:
                pass

    return False


def _tavily_to_results(tavily_results: Any, max_results: int) -> List[Dict[str, Any]]:
    fallback_results: List[Dict[str, Any]] = []
    if not isinstance(tavily_results, list):
        return fallback_results
    for idx, item in enumerate(tavily_results[:max_results], 1):
        if not isinstance(item, dict):
            continue
        fallback_results.append({
            "position": idx,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": (item.get("summary") or item.get("snippet") or item.get("raw_excerpt") or "")[:500],
        })
    return fallback_results


def _normalize_api_results(results: Any, max_results: int) -> List[Dict[str, Any]]:
    """
    Normalize results from different API search providers into the sandbox schema.

    Expected output keys: position/title/url/snippet
    """
    if not isinstance(results, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(results[: max(1, int(max_results or 10))], 1):
        if not isinstance(item, dict):
            continue

        title = item.get("title") or item.get("name") or ""
        url = item.get("url") or item.get("link") or item.get("href") or ""
        snippet = (
            item.get("snippet")
            or item.get("summary")
            or item.get("raw_excerpt")
            or item.get("content")
            or ""
        )

        try:
            position = int(item.get("position") or idx)
        except Exception:
            position = idx

        normalized.append(
            {
                "position": position,
                "title": str(title or ""),
                "url": str(url or ""),
                "snippet": str(snippet or "")[:500],
            }
        )

    return normalized


def _render_results_html(query: str, results: List[Dict[str, Any]], *, source: str = "tavily") -> str:
    """Render a simple HTML page to visualize search results (avoids captcha pages)."""
    import html as _html

    safe_query = _html.escape(query or "")
    items = []
    for r in results:
        title = _html.escape(str(r.get("title", "") or ""))
        url = _html.escape(str(r.get("url", "") or ""))
        snippet = _html.escape(str(r.get("snippet", "") or ""))
        pos = int(r.get("position") or 0)
        items.append(
            f"""
            <div class="result">
              <div class="title"><a href="{url}" data-weaver-result-index="{pos}">{title or url}</a></div>
              <div class="url">{url}</div>
              <div class="snippet">{snippet}</div>
            </div>
            """.strip()
        )

    joined = "\n".join(items) if items else "<div class='empty'>No results.</div>"
    safe_source = _html.escape(source or "tavily")
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Search Results</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #ffffff;
        --fg: #111827;
        --muted: #6b7280;
        --border: #e5e7eb;
        --link: #2563eb;
        --card: #f9fafb;
      }}
      body {{
        margin: 0;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji",
          "Segoe UI Emoji";
        background: var(--bg);
        color: var(--fg);
      }}
      .wrap {{
        max-width: 980px;
        margin: 0 auto;
        padding: 20px 18px 40px;
      }}
      .header {{
        display: flex;
        flex-direction: column;
        gap: 8px;
        padding: 14px 16px;
        border: 1px solid var(--border);
        border-radius: 12px;
        background: var(--card);
      }}
      .header .q {{
        font-size: 18px;
        font-weight: 650;
        line-height: 1.2;
      }}
      .header .meta {{
        font-size: 12px;
        color: var(--muted);
      }}
      .result {{
        padding: 14px 2px;
        border-bottom: 1px solid var(--border);
      }}
      .title a {{
        color: var(--link);
        text-decoration: none;
        font-size: 16px;
        font-weight: 600;
      }}
      .url {{
        font-size: 12px;
        color: #047857;
        margin-top: 4px;
        word-break: break-all;
      }}
      .snippet {{
        font-size: 13px;
        color: var(--muted);
        margin-top: 6px;
        line-height: 1.45;
      }}
      .empty {{
        padding: 24px 0;
        color: var(--muted);
        font-size: 13px;
      }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="header">
        <div class="q">{safe_query}</div>
        <div class="meta">Source: {safe_source} · Generated by Weaver</div>
      </div>
      <div class="results">
        {joined}
      </div>
    </div>
  </body>
</html>
"""


def _render_loading_html(query: str, *, source: str = "tavily", message: str = "Searching...") -> str:
    """Render an animated loading page so Live view shows progress while API tools run."""
    import html as _html

    safe_query = _html.escape(query or "")
    safe_source = _html.escape(source or "tavily")
    safe_message = _html.escape(message or "Searching...")
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Searching…</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #ffffff;
        --fg: #111827;
        --muted: #6b7280;
        --border: #e5e7eb;
        --card: #f9fafb;
        --accent: #2563eb;
      }}
      body {{
        margin: 0;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
        background: var(--bg);
        color: var(--fg);
      }}
      .wrap {{
        max-width: 980px;
        margin: 0 auto;
        padding: 20px 18px 40px;
      }}
      .card {{
        border: 1px solid var(--border);
        border-radius: 12px;
        background: var(--card);
        padding: 16px;
      }}
      .q {{
        font-size: 18px;
        font-weight: 650;
        line-height: 1.2;
        margin-bottom: 8px;
      }}
      .meta {{
        font-size: 12px;
        color: var(--muted);
        margin-bottom: 14px;
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
        border: 3px solid rgba(37, 99, 235, 0.25);
        border-top-color: var(--accent);
        animation: spin 0.9s linear infinite;
      }}
      @keyframes spin {{
        to {{ transform: rotate(360deg); }}
      }}
      .msg {{
        font-size: 13px;
        color: var(--muted);
      }}
      .hint {{
        margin-top: 10px;
        font-size: 12px;
        color: var(--muted);
      }}
      .bar {{
        margin-top: 14px;
        height: 8px;
        border-radius: 999px;
        background: rgba(37, 99, 235, 0.12);
        overflow: hidden;
      }}
      .bar > div {{
        height: 100%;
        width: 40%;
        background: rgba(37, 99, 235, 0.55);
        animation: slide 1.3s ease-in-out infinite;
      }}
      @keyframes slide {{
        0% {{ transform: translateX(-60%); }}
        50% {{ transform: translateX(160%); }}
        100% {{ transform: translateX(160%); }}
      }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="card">
        <div class="q">{safe_query}</div>
        <div class="meta">Source: {safe_source}</div>
        <div class="row">
          <div class="spinner" aria-hidden="true"></div>
          <div class="msg">{safe_message}</div>
        </div>
        <div class="bar" aria-hidden="true"><div></div></div>
        <div class="hint">Live view will update automatically while results are being prepared.</div>
      </div>
    </div>
  </body>
</html>
"""


@dataclass
class SearchResult:
    """A single search result."""
    title: str
    url: str
    snippet: str
    position: int


@dataclass
class SearchResults:
    """Collection of search results."""
    query: str
    engine: str
    results: List[SearchResult] = field(default_factory=list)
    total_results: int = 0
    screenshot_url: Optional[str] = None
    page_url: Optional[str] = None


def _get_event_emitter(thread_id: str):
    """Get event emitter for a thread (lazy import to avoid circular deps)."""
    from agent.core.events import get_emitter_sync

    return get_emitter_sync(thread_id)


def _get_screenshot_service():
    """Get screenshot service (lazy import)."""
    from tools.io.screenshot_service import get_screenshot_service

    return get_screenshot_service()


class _SandboxWebSearchBaseTool(BaseTool):
    """Base class for sandbox web search tools."""

    thread_id: str = "default"
    emit_events: bool = True
    save_screenshots: bool = True

    def _session(self):
        return sandbox_browser_sessions.get((self.thread_id or "").strip() or "default")

    def _page(self):
        return self._session().get_page()

    def _page_info(self) -> Dict[str, str]:
        page = self._page()
        title = ""
        try:
            title = page.title() or ""
        except Exception:
            pass
        url = ""
        try:
            url = page.url or ""
        except Exception:
            pass
        return {"url": url, "title": title}

    def _screenshot_with_save(
        self,
        action: str,
        full_page: bool = False,
    ) -> Dict[str, Any]:
        """Take screenshot, save to disk, and return URL (base64 fallback)."""
        page = self._page()
        try:
            png_bytes = page.screenshot(full_page=bool(full_page), animations="disabled", caret="hide")
        except TypeError:
            png_bytes = page.screenshot(full_page=bool(full_page))
        result: Dict[str, Any] = {"mime_type": "image/png"}

        if self.save_screenshots:
            service = _get_screenshot_service()
            if service:
                try:
                    # Use synchronous save method to avoid event loop conflicts
                    save_result = service.save_screenshot_sync(
                        image_data=png_bytes,
                        action=action,
                        thread_id=self.thread_id,
                        page_url=self._page_info().get("url"),
                    )

                    if save_result.get("url"):
                        result["screenshot_url"] = save_result["url"]
                        result["screenshot_filename"] = save_result.get("filename")
                        if save_result.get("mime_type"):
                            result["mime_type"] = save_result.get("mime_type")
                        logger.debug(f"[sandbox_search] Screenshot saved: {save_result['url']}")
                except Exception as e:
                    logger.warning(f"[sandbox_search] Failed to save screenshot: {e}")

        # Only include base64 when we couldn't persist to disk.
        if not result.get("screenshot_url"):
            result["image"] = base64.b64encode(png_bytes).decode("ascii")

        return result

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event (synchronous version)."""
        if not self.emit_events:
            return

        emitter = _get_event_emitter(self.thread_id)
        if not emitter:
            return

        try:
            # Use synchronous emit method to avoid event loop conflicts
            emitter.emit_sync(event_type, data)
        except Exception as e:
            logger.warning(f"[sandbox_search] Failed to emit event: {e}")

    def _emit_tool_start(self, action: str, args: Dict[str, Any]) -> float:
        """Emit tool start event and return start time."""
        start_time = time.time()
        self._emit_event("tool_start", {
            "tool": self.name,
            "action": action,
            "args": args,
            "thread_id": self.thread_id,
        })
        return start_time

    def _emit_tool_result(
        self,
        action: str,
        result: Dict[str, Any],
        start_time: float,
        success: bool = True,
    ) -> None:
        """Emit tool result event."""
        duration_ms = (time.time() - start_time) * 1000
        self._emit_event("tool_result", {
            "tool": self.name,
            "action": action,
            "success": success,
            "duration_ms": round(duration_ms, 2),
            "result_keys": list(result.keys()),
        })

    def _emit_screenshot(self, screenshot_data: Dict[str, Any], action: str) -> None:
        """Emit screenshot event (URL preferred, base64 fallback)."""
        url = screenshot_data.get("screenshot_url")
        image = screenshot_data.get("image")
        if not url and not image:
            return
        self._emit_event("tool_screenshot", {
            "tool": self.name,
            "action": action,
            "url": url,
            "image": image if not url else None,  # keep stream light when URL exists
            "filename": screenshot_data.get("screenshot_filename"),
            "mime_type": screenshot_data.get("mime_type"),
            "page_url": self._page_info().get("url"),
        })

    def _emit_progress(self, message: str, progress: Optional[int] = None) -> None:
        """Emit progress event."""
        self._emit_event("tool_progress", {
            "tool": self.name,
            "message": message,
            "progress": progress,
        })


class SandboxWebSearchInput(BaseModel):
    """Input schema for sandbox web search."""
    query: str = Field(min_length=1, description="Search query")
    engine: Literal["tavily", "google", "bing", "duckduckgo"] = Field(
        default="duckduckgo",
        description="Browser engine to use when API search is unavailable/blocked"
    )
    max_results: int = Field(
        default=10,
        ge=1,
        le=30,
        description="Maximum number of results to return"
    )
    wait_ms: int = Field(
        default=2000,
        ge=500,
        le=10000,
        description="Wait time for page load in milliseconds"
    )


class SandboxWebSearchTool(_SandboxWebSearchBaseTool):
    """
    Perform web search using sandbox browser.

    This tool:
    1. Opens the search engine in sandbox browser
    2. Enters the search query
    3. Parses the search results
    4. Returns structured results with screenshot
    """

    name: str = "sandbox_web_search"
    description: str = (
        "Perform a web search (API providers per SEARCH_ENGINES preferred; browser engines as fallback). "
        "Returns structured search results with titles, URLs, and snippets, "
        "plus a screenshot of the search results page. "
        "Use this for visual search process demonstration."
    )
    args_schema: type[BaseModel] = SandboxWebSearchInput

    def _run(
        self,
        query: str,
        engine: str = "duckduckgo",
        max_results: int = 10,
        wait_ms: int = 2000,
    ) -> Dict[str, Any]:
        """Execute the search."""
        def _impl() -> Dict[str, Any]:
            start_time = self._emit_tool_start("search", {
                "query": query,
                "engine": engine,
                "max_results": max_results,
            })

            # Prefer API-based search providers when available (configured via SEARCH_ENGINES in `.env`).
            try:
                from tools.search.fallback_search import run_fallback_search

                # Create the sandbox browser session early so Live view has something to show
                # while the API search is running.
                try:
                    page = self._page()
                    loading_html = _render_loading_html(
                        query,
                        source="auto",
                        message="Searching (API providers)...",
                    )
                    try:
                        page.set_content(loading_html, wait_until="domcontentloaded")
                    except TypeError:
                        page.set_content(loading_html)
                except Exception:
                    page = None

                self._emit_progress("使用 API 搜索...", 10)
                api_engine, api_results_raw = run_fallback_search(query=query, max_results=max_results)
                api_results = _normalize_api_results(api_results_raw, max_results)

                if api_results:
                    if page is None:
                        page = self._page()

                    html_page = _render_results_html(query, api_results, source=api_engine or "search")
                    try:
                        page.set_content(html_page, wait_until="domcontentloaded")
                    except TypeError:
                        page.set_content(html_page)
                    page.wait_for_timeout(100)

                    screenshot = self._screenshot_with_save("search_results", full_page=False)
                    self._emit_screenshot(screenshot, "search_results")

                    response = {
                        "query": query,
                        "engine": api_engine or "unknown",
                        "engine_requested": engine,
                        "page_url": page.url,
                        "total_results": len(api_results),
                        "results": api_results,
                    }
                    if screenshot.get("screenshot_url"):
                        response["screenshot_url"] = screenshot["screenshot_url"]
                    if screenshot.get("image"):
                        response["screenshot_base64"] = screenshot["image"]

                    self._emit_tool_result("search", response, start_time, success=True)
                    return response
            except Exception:
                # Best-effort: fall back to browser-based search below.
                pass

            engines_to_try = [engine]
            # In E2B sandbox, Bing may close the Chromium session; retry on DuckDuckGo for stability.
            if engine == "bing":
                engines_to_try.append("duckduckgo")

            last_error: Optional[Exception] = None
            for attempt_engine in engines_to_try:
                try:
                    # Get search engine config
                    engine_config = SEARCH_ENGINES.get(attempt_engine, SEARCH_ENGINES["duckduckgo"])
                    search_url = engine_config["url"].format(query=quote_plus(query))

                    # Emit progress: navigating
                    self._emit_progress(f"正在打开 {attempt_engine} 搜索...", 10)

                    # Navigate to search page
                    page = self._page()
                    page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

                    # Wait for results to load
                    self._emit_progress("等待搜索结果加载...", 30)
                    page.wait_for_timeout(int(wait_ms))

                    # Heuristic: detect captcha / anti-bot interstitials and fall back.
                    if _looks_like_antibot_challenge(page, engine_config):
                        raise RuntimeError(f"Search engine returned an anti-bot challenge: {attempt_engine}")

                    # Take screenshot of search results
                    self._emit_progress("正在截取搜索结果截图...", 50)
                    screenshot = self._screenshot_with_save("search_results", full_page=False)
                    self._emit_screenshot(screenshot, "search_results")

                    # Parse search results
                    self._emit_progress("正在解析搜索结果...", 70)
                    results = self._parse_search_results(page, engine_config, max_results)

                    # Build response
                    self._emit_progress("搜索完成", 100)

                    response = {
                        "query": query,
                        "engine": attempt_engine,
                        "page_url": page.url,
                        "total_results": len(results),
                        "results": results,
                    }

                    # Add screenshot info
                    if screenshot.get("screenshot_url"):
                        response["screenshot_url"] = screenshot["screenshot_url"]
                    if screenshot.get("image"):
                        response["screenshot_base64"] = screenshot["image"]

                    self._emit_tool_result("search", response, start_time, success=True)
                    return response

                except Exception as e:
                    last_error = e
                    sandbox_error = str(e)
                    logger.error(f"[sandbox_search] Search failed ({attempt_engine}): {sandbox_error}")

                    # If the Playwright page/context was closed, close the session so future calls can recover.
                    if _looks_like_browser_closed_error(e):
                        try:
                            self._session().close()
                        except Exception:
                            pass

                    # Retry with fallback engine when configured.
                    if attempt_engine != engines_to_try[-1]:
                        continue
                    break

            sandbox_error = str(last_error) if last_error else "Unknown error"

            # Best-effort fallback: use API search when sandbox browser is unavailable or blocked
            # (e.g., missing/invalid E2B_API_KEY or anti-bot interstitials).
            try:
                from tools.search.fallback_search import run_fallback_search

                api_engine, api_results_raw = run_fallback_search(query=query, max_results=max_results)
                fallback_results = _normalize_api_results(api_results_raw, max_results)

                response = {
                    "query": query,
                    "engine": api_engine or "unknown",
                    "engine_requested": engine,
                    "page_url": None,
                    "total_results": len(fallback_results),
                    "results": fallback_results,
                    "fallback": True,
                    "sandbox_error": sandbox_error,
                }

                # When browser search engines return captcha/challenge pages, still provide a useful
                # visualization by rendering API results into a simple HTML page and screenshot it.
                try:
                    self._emit_progress("搜索被拦截，使用 API 结果渲染页面...", 60)
                    page = self._page()
                    html_page = _render_results_html(query, fallback_results, source=api_engine or "search")
                    try:
                        page.set_content(html_page, wait_until="domcontentloaded")
                    except TypeError:
                        page.set_content(html_page)
                    page.wait_for_timeout(100)

                    screenshot = self._screenshot_with_save("search_results", full_page=False)
                    self._emit_screenshot(screenshot, "search_results")
                    if screenshot.get("screenshot_url"):
                        response["screenshot_url"] = screenshot["screenshot_url"]
                    if screenshot.get("image"):
                        response["screenshot_base64"] = screenshot["image"]
                    try:
                        response["page_url"] = page.url
                    except Exception:
                        pass
                except Exception:
                    # Rendering is best-effort; keep the text results even if the sandbox is unavailable.
                    pass

                # Consider fallback a successful tool response (even though the sandbox failed),
                # so the agent can continue reasoning with search results.
                self._emit_tool_result("search", response, start_time, success=True)
                return response

            except Exception as fallback_e:
                response = {
                    "query": query,
                    "engine": engine,
                    "page_url": None,
                    "total_results": 0,
                    "results": [],
                    "error": sandbox_error,
                    "fallback_error": str(fallback_e),
                }
                self._emit_tool_result("search", response, start_time, success=False)
                return response

        return sandbox_browser_sessions.run_sync(self.thread_id, _impl)

    def _parse_search_results(
        self,
        page,
        config: Dict[str, str],
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """Parse search results from the page."""
        results = []

        try:
            # Find all result containers
            result_selector = config.get("result_selector", "div.g")
            title_selector = config.get("title_selector", "h3")
            link_selector = config.get("link_selector", "a")
            snippet_selector = config.get("snippet_selector", "p")

            result_elements = page.locator(result_selector).all()

            for i, element in enumerate(result_elements[:max_results]):
                try:
                    # Extract title
                    title = ""
                    try:
                        title_el = element.locator(title_selector).first
                        title = title_el.inner_text(timeout=1000).strip()
                    except Exception:
                        pass

                    # Extract URL
                    url = ""
                    try:
                        link_el = element.locator(link_selector).first
                        url = link_el.get_attribute("href", timeout=1000) or ""
                        # Clean up Google redirect URLs
                        if url.startswith("/url?"):
                            match = re.search(r'[?&]q=([^&]+)', url)
                            if match:
                                url = match.group(1)
                    except Exception:
                        pass

                    # Extract snippet
                    snippet = ""
                    try:
                        snippet_el = element.locator(snippet_selector).first
                        snippet = snippet_el.inner_text(timeout=1000).strip()
                    except Exception:
                        pass

                    # Skip if no title or URL
                    if not title and not url:
                        continue

                    results.append({
                        "position": i + 1,
                        "title": title,
                        "url": url,
                        "snippet": snippet[:500] if snippet else "",
                    })

                except Exception as e:
                    logger.debug(f"[sandbox_search] Failed to parse result {i}: {e}")
                    continue

        except Exception as e:
            logger.warning(f"[sandbox_search] Failed to parse results: {e}")

        return results


class SandboxSearchAndClickInput(BaseModel):
    """Input for search and click action."""
    query: str = Field(min_length=1, description="Search query")
    result_index: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Which result to click (1-based index)"
    )
    engine: Literal["tavily", "google", "bing", "duckduckgo"] = Field(
        default="duckduckgo",
        description="Browser engine to use when API search is unavailable/blocked"
    )
    wait_ms: int = Field(default=3000, ge=500, le=15000)


class SandboxSearchAndClickTool(_SandboxWebSearchBaseTool):
    """
    Search and click on a specific result.

    This combines search + click into one action with full visualization.
    """

    name: str = "sandbox_search_and_click"
    description: str = (
        "Search the web (API providers per SEARCH_ENGINES preferred; browser engines as fallback) and click on a specific result. "
        "Combines search and navigation into one action. "
        "Returns screenshots of both search results and the clicked page."
    )
    args_schema: type[BaseModel] = SandboxSearchAndClickInput

    def _run(
        self,
        query: str,
        result_index: int = 1,
        engine: str = "duckduckgo",
        wait_ms: int = 3000,
    ) -> Dict[str, Any]:
        return sandbox_browser_sessions.run_sync(
            self.thread_id,
            self._run_impl,
            query=query,
            result_index=result_index,
            engine=engine,
            wait_ms=wait_ms,
        )

    def _run_impl(
        self,
        query: str,
        result_index: int = 1,
        engine: str = "duckduckgo",
        wait_ms: int = 3000,
    ) -> Dict[str, Any]:
        """Execute search and click."""
        start_time = self._emit_tool_start("search_and_click", {
            "query": query,
            "result_index": result_index,
            "engine": engine,
        })

        # Prefer API-based search when available to avoid captcha pages.
        try:
            from tools.search.fallback_search import run_fallback_search

            needed_results = max(10, int(result_index or 1))

            # Create the sandbox browser session early so Live view shows progress.
            try:
                page = self._page()
                loading_html = _render_loading_html(
                    query,
                    source="auto",
                    message="Searching (API providers)...",
                )
                try:
                    page.set_content(loading_html, wait_until="domcontentloaded")
                except TypeError:
                    page.set_content(loading_html)
            except Exception:
                page = None

            self._emit_progress("使用 API 搜索...", 10)
            api_engine, api_results_raw = run_fallback_search(query=query, max_results=needed_results)
            api_results = _normalize_api_results(api_results_raw, needed_results)

            if api_results:
                if result_index > len(api_results):
                    raise ValueError(f"只找到 {len(api_results)} 个结果，无法点击第 {result_index} 个")

                clicked = api_results[result_index - 1] if api_results else {}
                clicked_url = str(clicked.get("url") or "")
                clicked_title = str(clicked.get("title") or "")

                search_screenshot: Dict[str, Any] = {}
                dest_screenshot: Dict[str, Any] = {}
                destination_error: Optional[str] = None

                try:
                    if page is None:
                        page = self._page()
                    html_page = _render_results_html(query, api_results, source=api_engine or "search")
                    try:
                        page.set_content(html_page, wait_until="domcontentloaded")
                    except TypeError:
                        page.set_content(html_page)
                    page.wait_for_timeout(100)
                    search_screenshot = self._screenshot_with_save("search_page", full_page=False)
                    self._emit_screenshot(search_screenshot, "search_page")
                except Exception:
                    pass

                try:
                    if clicked_url:
                        self._emit_progress("打开目标页面...", 70)
                        page = self._page()
                        page.goto(clicked_url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(int(wait_ms))
                        dest_screenshot = self._screenshot_with_save("destination_page", full_page=False)
                        self._emit_screenshot(dest_screenshot, "destination_page")
                except Exception as e:
                    destination_error = str(e)

                page_info = self._page_info()
                response = {
                    "query": query,
                    "engine": api_engine or "unknown",
                    "engine_requested": engine,
                    "fallback": False,
                    "clicked_result": {
                        "position": result_index,
                        "title": clicked_title,
                        "url": clicked_url,
                    },
                    "destination": {
                        "url": page_info.get("url") or clicked_url,
                        "title": page_info.get("title"),
                    },
                    "screenshots": {
                        "search_page": search_screenshot.get("screenshot_url"),
                        "destination_page": dest_screenshot.get("screenshot_url"),
                    },
                }
                if destination_error:
                    response["destination_error"] = destination_error

                self._emit_tool_result("search_and_click", response, start_time, success=bool(clicked_url))
                return response
        except Exception:
            # Best-effort: fall back to browser-based flow below.
            pass

        engines_to_try = [engine]
        if engine == "bing":
            engines_to_try.append("duckduckgo")

        last_error: Optional[Exception] = None
        for attempt_engine in engines_to_try:
            try:
                # Get search engine config
                engine_config = SEARCH_ENGINES.get(attempt_engine, SEARCH_ENGINES["duckduckgo"])
                search_url = engine_config["url"].format(query=quote_plus(query))

                # Step 1: Navigate to search
                self._emit_progress("正在搜索...", 10)
                page = self._page()
                page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)

                # Heuristic: detect captcha / anti-bot interstitials and fall back.
                if _looks_like_antibot_challenge(page, engine_config):
                    raise RuntimeError(f"Search engine returned an anti-bot challenge: {attempt_engine}")

                # Screenshot search results
                self._emit_progress("正在截取搜索结果...", 30)
                search_screenshot = self._screenshot_with_save("search_page", full_page=False)
                self._emit_screenshot(search_screenshot, "search_page")

                # Step 2: Find and click the result
                self._emit_progress(f"正在点击第 {result_index} 个结果...", 50)

                result_selector = engine_config.get("result_selector", "div.g")
                link_selector = engine_config.get("link_selector", "a")

                # Get the nth result
                results = page.locator(result_selector).all()
                if result_index > len(results):
                    raise ValueError(f"只找到 {len(results)} 个结果，无法点击第 {result_index} 个")

                target_result = results[result_index - 1]
                link = target_result.locator(link_selector).first

                # Get link info before clicking
                clicked_url = link.get_attribute("href") or ""
                clicked_title = ""
                try:
                    title_selector = engine_config.get("title_selector", "h3")
                    clicked_title = target_result.locator(title_selector).first.inner_text(timeout=1000)
                except Exception:
                    pass

                # Click
                link.click(timeout=30000)

                # Wait for page load
                self._emit_progress("等待页面加载...", 70)
                page.wait_for_timeout(int(wait_ms))

                # Screenshot destination page
                self._emit_progress("正在截取目标页面...", 90)
                dest_screenshot = self._screenshot_with_save("destination_page", full_page=False)
                self._emit_screenshot(dest_screenshot, "destination_page")

                # Build response
                self._emit_progress("完成", 100)

                page_info = self._page_info()
                response = {
                    "query": query,
                    "engine": attempt_engine,
                    "clicked_result": {
                        "position": result_index,
                        "title": clicked_title,
                        "url": clicked_url,
                    },
                    "destination": {
                        "url": page_info.get("url"),
                        "title": page_info.get("title"),
                    },
                    "screenshots": {
                        "search_page": search_screenshot.get("screenshot_url"),
                        "destination_page": dest_screenshot.get("screenshot_url"),
                    },
                }

                self._emit_tool_result("search_and_click", response, start_time, success=True)
                return response

            except Exception as e:
                last_error = e
                err = str(e)
                logger.error(f"[sandbox_search] Search and click failed ({attempt_engine}): {err}")
                if _looks_like_browser_closed_error(e):
                    try:
                        self._session().close()
                    except Exception:
                        pass

                if attempt_engine != engines_to_try[-1]:
                    continue
                break

        sandbox_error = str(last_error) if last_error else "Unknown error"

        # Fallback: use Tavily API search, then render results into a local HTML page so the UI
        # still gets a meaningful screenshot (avoids captcha pages).
        try:
            from tools.search.search import tavily_search

            tavily_results = tavily_search.invoke({"query": query, "max_results": max(10, int(result_index or 1))})
            fallback_results: List[Dict[str, Any]] = []
            if isinstance(tavily_results, list):
                for idx, item in enumerate(tavily_results[: max(10, int(result_index or 1))], 1):
                    if not isinstance(item, dict):
                        continue
                    fallback_results.append({
                        "position": idx,
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": (item.get("summary") or item.get("snippet") or "")[:500],
                    })

            if result_index > len(fallback_results):
                raise ValueError(f"只找到 {len(fallback_results)} 个结果，无法点击第 {result_index} 个")

            clicked = fallback_results[result_index - 1] if fallback_results else {}
            clicked_url = str(clicked.get("url") or "")
            clicked_title = str(clicked.get("title") or "")

            search_screenshot: Dict[str, Any] = {}
            dest_screenshot: Dict[str, Any] = {}
            destination_error: Optional[str] = None

            try:
                self._emit_progress("搜索被拦截，使用 Tavily 结果...", 30)
                page = self._page()
                html_page = _render_results_html(query, fallback_results, source="tavily")
                try:
                    page.set_content(html_page, wait_until="domcontentloaded")
                except TypeError:
                    page.set_content(html_page)
                page.wait_for_timeout(100)
                search_screenshot = self._screenshot_with_save("search_page", full_page=False)
                self._emit_screenshot(search_screenshot, "search_page")
            except Exception:
                pass

            try:
                if clicked_url:
                    self._emit_progress("打开目标页面...", 70)
                    page = self._page()
                    page.goto(clicked_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(int(wait_ms))
                    dest_screenshot = self._screenshot_with_save("destination_page", full_page=False)
                    self._emit_screenshot(dest_screenshot, "destination_page")
            except Exception as e:
                destination_error = str(e)

            page_info = self._page_info()
            response = {
                "query": query,
                "engine": "tavily",
                "fallback": True,
                "sandbox_error": sandbox_error,
                "clicked_result": {
                    "position": result_index,
                    "title": clicked_title,
                    "url": clicked_url,
                },
                "destination": {
                    "url": page_info.get("url") or clicked_url,
                    "title": page_info.get("title"),
                },
                "screenshots": {
                    "search_page": search_screenshot.get("screenshot_url"),
                    "destination_page": dest_screenshot.get("screenshot_url"),
                },
            }
            if destination_error:
                response["destination_error"] = destination_error

            # Treat fallback as successful if we have at least a clicked URL; the agent can continue.
            self._emit_tool_result("search_and_click", response, start_time, success=bool(clicked_url))
            return response

        except Exception as fallback_e:
            response = {
                "query": query,
                "engine": engine,
                "error": sandbox_error,
                "fallback_error": str(fallback_e),
            }
            self._emit_tool_result("search_and_click", response, start_time, success=False)
            return response


class SandboxExtractSearchResultsInput(BaseModel):
    """Input for extracting search results from current page."""
    max_results: int = Field(default=10, ge=1, le=30)


class SandboxExtractSearchResultsTool(_SandboxWebSearchBaseTool):
    """
    Extract search results from the current browser page.

    Useful if you've already navigated to a search page manually.
    """

    name: str = "sandbox_extract_search_results"
    description: str = (
        "Extract search results from the current browser page. "
        "Use this if you've already navigated to a search results page."
    )
    args_schema: type[BaseModel] = SandboxExtractSearchResultsInput

    def _run(self, max_results: int = 10) -> Dict[str, Any]:
        return sandbox_browser_sessions.run_sync(
            self.thread_id,
            self._run_impl,
            max_results=max_results,
        )

    def _run_impl(self, max_results: int = 10) -> Dict[str, Any]:
        """Extract results from current page."""
        start_time = self._emit_tool_start("extract_results", {"max_results": max_results})

        try:
            page = self._page()
            page_url = page.url

            # Detect search engine from URL
            engine = "unknown"
            engine_config = None

            if "google.com" in page_url:
                engine = "google"
                engine_config = SEARCH_ENGINES["google"]
            elif "bing.com" in page_url:
                engine = "bing"
                engine_config = SEARCH_ENGINES["bing"]
            elif "duckduckgo.com" in page_url:
                engine = "duckduckgo"
                engine_config = SEARCH_ENGINES["duckduckgo"]

            results = []
            if engine_config:
                # Use known search engine parser
                results = self._parse_results_with_config(page, engine_config, max_results)
            else:
                # Generic extraction
                results = self._parse_results_generic(page, max_results)

            # Take screenshot
            screenshot = self._screenshot_with_save("extract_results", full_page=False)
            self._emit_screenshot(screenshot, "extract_results")

            response = {
                "page_url": page_url,
                "detected_engine": engine,
                "total_results": len(results),
                "results": results,
            }

            if screenshot.get("screenshot_url"):
                response["screenshot_url"] = screenshot["screenshot_url"]

            self._emit_tool_result("extract_results", response, start_time, success=True)
            return response

        except Exception as e:
            err = str(e)
            logger.error(f"[sandbox_search] Extract failed: {err}")
            response = {
                "page_url": None,
                "detected_engine": "unknown",
                "total_results": 0,
                "results": [],
                "error": err,
                "requires": "E2B_API_KEY",
            }
            self._emit_tool_result("extract_results", response, start_time, success=False)
            return response

    def _parse_results_with_config(
        self,
        page,
        config: Dict[str, str],
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """Parse using search engine config."""
        results = []

        result_selector = config.get("result_selector", "div.g")
        title_selector = config.get("title_selector", "h3")
        link_selector = config.get("link_selector", "a")
        snippet_selector = config.get("snippet_selector", "p")

        try:
            elements = page.locator(result_selector).all()

            for i, element in enumerate(elements[:max_results]):
                try:
                    title = ""
                    url = ""
                    snippet = ""

                    try:
                        title = element.locator(title_selector).first.inner_text(timeout=1000).strip()
                    except Exception:
                        pass

                    try:
                        url = element.locator(link_selector).first.get_attribute("href", timeout=1000) or ""
                    except Exception:
                        pass

                    try:
                        snippet = element.locator(snippet_selector).first.inner_text(timeout=1000).strip()
                    except Exception:
                        pass

                    if title or url:
                        results.append({
                            "position": i + 1,
                            "title": title,
                            "url": url,
                            "snippet": snippet[:500] if snippet else "",
                        })
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"[sandbox_search] Config-based parsing failed: {e}")

        return results

    def _parse_results_generic(self, page, max_results: int) -> List[Dict[str, Any]]:
        """Generic result extraction."""
        results = []

        try:
            # Try to find links with titles
            links = page.locator("a").all()

            seen_urls = set()
            for i, link in enumerate(links):
                if len(results) >= max_results:
                    break

                try:
                    url = link.get_attribute("href", timeout=500) or ""
                    text = link.inner_text(timeout=500).strip()

                    # Filter out navigation/footer links
                    if not url or not text:
                        continue
                    if url in seen_urls:
                        continue
                    if len(text) < 10 or len(text) > 200:
                        continue
                    if url.startswith("#") or url.startswith("javascript:"):
                        continue

                    seen_urls.add(url)
                    results.append({
                        "position": len(results) + 1,
                        "title": text,
                        "url": url,
                        "snippet": "",
                    })
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"[sandbox_search] Generic parsing failed: {e}")

        return results


def build_sandbox_web_search_tools(
    thread_id: str,
    emit_events: bool = True,
    save_screenshots: bool = True,
) -> List[BaseTool]:
    """
    Build sandbox web search tools for a thread.

    Args:
        thread_id: Thread/conversation ID
        emit_events: Whether to emit events for visualization
        save_screenshots: Whether to save screenshots to disk

    Returns:
        List of search tools
    """
    return [
        SandboxWebSearchTool(
            thread_id=thread_id,
            emit_events=emit_events,
            save_screenshots=save_screenshots,
        ),
        SandboxSearchAndClickTool(
            thread_id=thread_id,
            emit_events=emit_events,
            save_screenshots=save_screenshots,
        ),
        SandboxExtractSearchResultsTool(
            thread_id=thread_id,
            emit_events=emit_events,
            save_screenshots=save_screenshots,
        ),
    ]
