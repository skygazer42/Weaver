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
        """Take screenshot, save to disk, and return both base64 and URL."""
        page = self._page()
        png_bytes = page.screenshot(full_page=bool(full_page))
        b64_image = base64.b64encode(png_bytes).decode("ascii")

        result = {"image": b64_image}

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
                        logger.debug(f"[sandbox_search] Screenshot saved: {save_result['url']}")
                except Exception as e:
                    logger.warning(f"[sandbox_search] Failed to save screenshot: {e}")

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
        """Emit screenshot event if URL is available."""
        if screenshot_data.get("screenshot_url"):
            self._emit_event("tool_screenshot", {
                "tool": self.name,
                "action": action,
                "url": screenshot_data["screenshot_url"],
                "filename": screenshot_data.get("screenshot_filename"),
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
    engine: Literal["google", "bing", "duckduckgo"] = Field(
        default="bing",
        description="Search engine to use"
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
        "Perform a web search using a sandboxed browser (Google/Bing/DuckDuckGo). "
        "Returns structured search results with titles, URLs, and snippets, "
        "plus a screenshot of the search results page. "
        "Use this for visual search process demonstration."
    )
    args_schema: type[BaseModel] = SandboxWebSearchInput

    def _run(
        self,
        query: str,
        engine: str = "google",
        max_results: int = 10,
        wait_ms: int = 2000,
    ) -> Dict[str, Any]:
        """Execute the search."""
        start_time = self._emit_tool_start("search", {
            "query": query,
            "engine": engine,
            "max_results": max_results,
        })

        try:
            # Get search engine config
            engine_config = SEARCH_ENGINES.get(engine, SEARCH_ENGINES["bing"])
            search_url = engine_config["url"].format(query=quote_plus(query))

            # Emit progress: navigating
            self._emit_progress(f"正在打开 {engine} 搜索...", 10)

            # Navigate to search page
            page = self._page()
            page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

            # Wait for results to load
            self._emit_progress("等待搜索结果加载...", 30)
            page.wait_for_timeout(int(wait_ms))

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
                "engine": engine,
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
            logger.error(f"[sandbox_search] Search failed: {e}")
            self._emit_tool_result("search", {"error": str(e)}, start_time, success=False)
            raise

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
    engine: Literal["google", "bing", "duckduckgo"] = Field(
        default="bing",
        description="Search engine to use"
    )
    wait_ms: int = Field(default=3000, ge=500, le=15000)


class SandboxSearchAndClickTool(_SandboxWebSearchBaseTool):
    """
    Search and click on a specific result.

    This combines search + click into one action with full visualization.
    """

    name: str = "sandbox_search_and_click"
    description: str = (
        "Search the web and click on a specific result. "
        "Combines search and navigation into one action. "
        "Returns screenshots of both search results and the clicked page."
    )
    args_schema: type[BaseModel] = SandboxSearchAndClickInput

    def _run(
        self,
        query: str,
        result_index: int = 1,
        engine: str = "google",
        wait_ms: int = 3000,
    ) -> Dict[str, Any]:
        """Execute search and click."""
        start_time = self._emit_tool_start("search_and_click", {
            "query": query,
            "result_index": result_index,
            "engine": engine,
        })

        try:
            # Get search engine config
            engine_config = SEARCH_ENGINES.get(engine, SEARCH_ENGINES["bing"])
            search_url = engine_config["url"].format(query=quote_plus(query))

            # Step 1: Navigate to search
            self._emit_progress("正在搜索...", 10)
            page = self._page()
            page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)

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
                "engine": engine,
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
            logger.error(f"[sandbox_search] Search and click failed: {e}")
            self._emit_tool_result("search_and_click", {"error": str(e)}, start_time, success=False)
            raise


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
            logger.error(f"[sandbox_search] Extract failed: {e}")
            self._emit_tool_result("extract_results", {"error": str(e)}, start_time, success=False)
            raise

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
