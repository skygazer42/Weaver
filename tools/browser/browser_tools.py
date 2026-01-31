from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from agent.core.events import ToolEventType, get_emitter_sync
from tools.browser.browser_use_events import emit_progress

from .browser_session import browser_sessions

logger = logging.getLogger(__name__)


def _trim(text: str, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


class _BrowserTool(BaseTool):
    thread_id: str = "default"

    def _session(self):
        return browser_sessions.get((self.thread_id or "").strip() or "default")

    def _emit(self, event_type: ToolEventType, data: Dict[str, Any]):
        emitter = get_emitter_sync(self.thread_id)
        try:
            emitter.emit_sync(event_type, data)
        except Exception:
            pass

    def _progress(self, action: str, info: str):
        emit_progress(self.thread_id, self.name, action, info)

    def _maybe_emit_screenshot(
        self,
        *,
        page_url: str,
        action: str,
        full_page: bool = False,
        wait_ms: int = 1200,
    ) -> None:
        """
        Best-effort screenshot emission for lightweight browser tools.

        This keeps the "browser_*" tools JS-free for content extraction but still
        emits a visual screenshot event when the agent opens a URL, so the UI can
        show the page in BrowserViewer.
        """
        target = (page_url or "").strip()
        if not target.startswith(("http://", "https://")):
            return

        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception:
            # Playwright isn't available; skip silently.
            return

        png_bytes: Optional[bytes] = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page(viewport={"width": 1280, "height": 720})
                    page.goto(target, wait_until="networkidle", timeout=30000)
                    if wait_ms:
                        page.wait_for_timeout(int(wait_ms))
                    try:
                        png_bytes = page.screenshot(
                            full_page=bool(full_page),
                            type="jpeg",
                            quality=85,
                            animations="disabled",
                            caret="hide",
                        )
                    except TypeError:
                        # Backwards-compat: older Playwright builds may not support animations/caret options.
                        png_bytes = page.screenshot(
                            full_page=bool(full_page), type="jpeg", quality=85
                        )
                finally:
                    browser.close()
        except Exception as e:
            # Don't fail the primary tool action.
            logger.debug("[browser_tools] screenshot skipped: %s", e)
            return

        if not png_bytes:
            return

        screenshot_url: Optional[str] = None
        screenshot_filename: Optional[str] = None
        mime_type: str = "image/jpeg"
        image_b64: Optional[str] = None

        try:
            from tools.io.screenshot_service import get_screenshot_service

            save_result = get_screenshot_service().save_screenshot_sync(
                image_data=png_bytes,
                action=f"{self.name}_{action}",
                thread_id=self.thread_id,
                page_url=target,
            )
            screenshot_url = save_result.get("url")
            screenshot_filename = save_result.get("filename")
            mime_type = save_result.get("mime_type") or mime_type
        except Exception:
            image_b64 = base64.b64encode(png_bytes).decode("ascii")

        try:
            self._emit(
                ToolEventType.TOOL_SCREENSHOT,
                {
                    "tool": self.name,
                    "action": action,
                    "url": screenshot_url,
                    "filename": screenshot_filename,
                    "page_url": target,
                    "mime_type": mime_type,
                    # Only include base64 when we couldn't persist to disk.
                    "image": None if screenshot_url else image_b64,
                },
            )
        except Exception:
            pass


class BrowserSearchInput(BaseModel):
    query: str = Field(min_length=1)
    engine: str = Field(default="duckduckgo", description="duckduckgo|bing")
    max_links: int = Field(default=10, ge=1, le=30)


class BrowserSearchTool(_BrowserTool):
    name: str = "browser_search"
    description: str = (
        "Search the web in a lightweight browser session (JS-free). "
        "Returns the search page URL plus extracted links."
    )
    args_schema: type[BaseModel] = BrowserSearchInput

    def _run(self, query: str, engine: str = "duckduckgo", max_links: int = 10) -> Dict[str, Any]:
        self._progress("search", f"{engine} {query}")
        self._emit(
            ToolEventType.TOOL_START,
            {"tool": self.name, "args": {"query": query, "engine": engine}},
        )
        page = self._session().search(query=query, engine=engine)
        q = " ".join((query or "").split())
        self._maybe_emit_screenshot(page_url=page.url, action=f"search:{engine} {_trim(q, 40)}")
        return {
            "url": page.url,
            "title": page.title,
            "links": page.links[: int(max_links)],
            "text_excerpt": _trim(page.text, 1200),
        }


class BrowserNavigateInput(BaseModel):
    url: str = Field(min_length=1)
    max_links: int = Field(default=10, ge=0, le=30)


class BrowserNavigateTool(_BrowserTool):
    name: str = "browser_navigate"
    description: str = "Open a URL in the lightweight browser session and extract title/text/links."
    args_schema: type[BaseModel] = BrowserNavigateInput

    def _run(self, url: str, max_links: int = 10) -> Dict[str, Any]:
        self._progress("navigate", url)
        self._emit(ToolEventType.TOOL_START, {"tool": self.name, "args": {"url": url}})
        page = self._session().navigate(url=url)
        try:
            from urllib.parse import urlparse

            host = urlparse(page.url or "").netloc
        except Exception:
            host = ""
        self._maybe_emit_screenshot(page_url=page.url, action=f"open:{host}" if host else "open")
        return {
            "url": page.url,
            "title": page.title,
            "links": page.links[: int(max_links)],
            "text_excerpt": _trim(page.text, 1600),
        }


class BrowserClickInput(BaseModel):
    index: int = Field(ge=1, description="1-based link index from the last page links list")
    max_links: int = Field(default=10, ge=0, le=30)


class BrowserClickTool(_BrowserTool):
    name: str = "browser_click"
    description: str = "Click a link from the current page by 1-based index and navigate to it."
    args_schema: type[BaseModel] = BrowserClickInput

    def _run(self, index: int, max_links: int = 10) -> Dict[str, Any]:
        session = self._session()
        if not session.current:
            raise ValueError("No current page. Use browser_search or browser_navigate first.")
        links = session.current.links or []
        idx = int(index) - 1
        if idx < 0 or idx >= len(links):
            raise ValueError(f"index out of range (1-{len(links)})")
        url = links[idx].get("url") or ""
        self._progress("click", f"{index} -> {url}")
        self._emit(
            ToolEventType.TOOL_START, {"tool": self.name, "args": {"index": index, "url": url}}
        )
        page = session.navigate(url=url)
        try:
            from urllib.parse import urlparse

            host = urlparse(page.url or "").netloc
        except Exception:
            host = ""
        self._maybe_emit_screenshot(
            page_url=page.url, action=f"open#{index}:{host}" if host else f"open#{index}"
        )
        return {
            "clicked": links[idx],
            "url": page.url,
            "title": page.title,
            "links": page.links[: int(max_links)],
            "text_excerpt": _trim(page.text, 1600),
        }


class BrowserBackTool(_BrowserTool):
    name: str = "browser_back"
    description: str = "Go back to the previous page in this browser session."

    def _run(self) -> Dict[str, Any]:
        self._emit(ToolEventType.TOOL_START, {"tool": self.name})
        page = self._session().back()
        self._maybe_emit_screenshot(page_url=page.url, action="back")
        return {
            "url": page.url,
            "title": page.title,
            "links": page.links[:10],
            "text_excerpt": _trim(page.text, 1200),
        }


class BrowserExtractTextInput(BaseModel):
    max_chars: int = Field(default=3000, ge=200, le=20000)


class BrowserExtractTextTool(_BrowserTool):
    name: str = "browser_extract_text"
    description: str = "Return the extracted text of the current page."
    args_schema: type[BaseModel] = BrowserExtractTextInput

    def _run(self, max_chars: int = 3000) -> Dict[str, Any]:
        session = self._session()
        if not session.current:
            raise ValueError("No current page. Use browser_search or browser_navigate first.")
        self._emit(ToolEventType.TOOL_START, {"tool": self.name})
        return {
            "url": session.current.url,
            "title": session.current.title,
            "text": _trim(session.current.text, int(max_chars)),
        }


class BrowserListLinksInput(BaseModel):
    max_links: int = Field(default=10, ge=1, le=30)


class BrowserListLinksTool(_BrowserTool):
    name: str = "browser_list_links"
    description: str = "List extracted links from the current page."
    args_schema: type[BaseModel] = BrowserListLinksInput

    def _run(self, max_links: int = 10) -> Dict[str, Any]:
        session = self._session()
        if not session.current:
            raise ValueError("No current page. Use browser_search or browser_navigate first.")
        self._emit(ToolEventType.TOOL_START, {"tool": self.name})
        return {
            "url": session.current.url,
            "title": session.current.title,
            "links": session.current.links[: int(max_links)],
        }


class BrowserResetTool(_BrowserTool):
    name: str = "browser_reset"
    description: str = "Reset the browser session (clears current page and history)."

    def _run(self) -> Dict[str, Any]:
        self._emit(ToolEventType.TOOL_START, {"tool": self.name})
        browser_sessions.reset(self.thread_id)
        return {"status": "reset", "thread_id": self.thread_id}


class BrowserScreenshotInput(BaseModel):
    url: Optional[str] = Field(default=None, description="If omitted, uses current page url")
    full_page: bool = True
    wait_ms: int = Field(default=1500, ge=0, le=15000)


class BrowserScreenshotTool(_BrowserTool):
    name: str = "browser_screenshot"
    description: str = (
        "Take a real browser screenshot (requires Playwright + installed browsers). "
        "Returns `screenshot_url` when available (base64 fallback in `image`)."
    )
    args_schema: type[BaseModel] = BrowserScreenshotInput

    def _run(
        self, url: Optional[str] = None, full_page: bool = True, wait_ms: int = 1500
    ) -> Dict[str, Any]:
        target = (url or "").strip()
        if not target:
            session = self._session()
            if not session.current or not session.current.url:
                raise ValueError("No url provided and no current page. Use browser_navigate first.")
            target = session.current.url

        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "Playwright is required for screenshots. Install: pip install playwright; "
                "then run: python -m playwright install chromium"
            ) from e

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 720})
                page.goto(target, wait_until="networkidle", timeout=30000)
                if wait_ms:
                    page.wait_for_timeout(int(wait_ms))
                try:
                    png_bytes = page.screenshot(
                        full_page=bool(full_page), animations="disabled", caret="hide"
                    )
                except TypeError:
                    png_bytes = page.screenshot(full_page=bool(full_page))
            finally:
                browser.close()

        screenshot_url: Optional[str] = None
        screenshot_filename: Optional[str] = None
        mime_type: str = "image/png"

        # Best-effort: save to disk so the UI can fetch the image by URL (lighter than SSE base64).
        try:
            from tools.io.screenshot_service import get_screenshot_service

            save_result = get_screenshot_service().save_screenshot_sync(
                image_data=png_bytes,
                action="browser_screenshot",
                thread_id=self.thread_id,
                page_url=target,
            )
            screenshot_url = save_result.get("url")
            screenshot_filename = save_result.get("filename")
            mime_type = save_result.get("mime_type") or mime_type
        except Exception:
            pass

        # Only include base64 when we couldn't persist to disk.
        image_b64: Optional[str] = None
        if not screenshot_url:
            image_b64 = base64.b64encode(png_bytes).decode("ascii")

        # Emit screenshot event for front-end visualization
        try:
            self._emit(
                ToolEventType.TOOL_SCREENSHOT,
                {
                    "tool": self.name,
                    "action": "screenshot",
                    "url": screenshot_url,
                    "filename": screenshot_filename,
                    "page_url": target,
                    "mime_type": mime_type,
                    # Only include base64 when we couldn't persist to disk.
                    "image": image_b64,
                },
            )
        except Exception:
            pass

        result: Dict[str, Any] = {
            "url": target,  # page URL (kept for backwards compatibility)
            "page_url": target,
            "screenshot_url": screenshot_url,
            "filename": screenshot_filename,
            "mime_type": mime_type,
        }
        if image_b64:
            result["image"] = image_b64
        return result


def build_browser_tools(thread_id: str) -> List[BaseTool]:
    """
    Create per-request browser tools bound to a thread_id.
    """
    return [
        BrowserSearchTool(thread_id=thread_id),
        BrowserNavigateTool(thread_id=thread_id),
        BrowserClickTool(thread_id=thread_id),
        BrowserBackTool(thread_id=thread_id),
        BrowserExtractTextTool(thread_id=thread_id),
        BrowserListLinksTool(thread_id=thread_id),
        BrowserScreenshotTool(thread_id=thread_id),
        BrowserResetTool(thread_id=thread_id),
    ]
