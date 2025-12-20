"""
Sandbox Browser Tools with Event Emission and Screenshot Saving.

This module provides browser automation tools that:
- Emit real-time events for visualization (tool_start, tool_screenshot, tool_result)
- Save screenshots to disk and return URLs
- Support both sync and async event emission

Usage:
    from tools.sandbox.sandbox_browser_tools import build_sandbox_browser_tools

    tools = build_sandbox_browser_tools(thread_id="thread_123")
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .sandbox_browser_session import sandbox_browser_sessions

logger = logging.getLogger(__name__)


def _trim(text: str, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _get_event_emitter(thread_id: str):
    """Get event emitter for a thread (lazy import to avoid circular deps)."""
    try:
        from agent.events import get_emitter_sync
        return get_emitter_sync(thread_id)
    except ImportError:
        return None


def _get_screenshot_service():
    """Get screenshot service (lazy import)."""
    try:
        from tools.screenshot_service import get_screenshot_service
        return get_screenshot_service()
    except ImportError:
        return None


class _SbBrowserTool(BaseTool):
    """Base class for sandbox browser tools with event emission support."""

    thread_id: str = "default"
    emit_events: bool = True  # Whether to emit events
    save_screenshots: bool = True  # Whether to save screenshots to disk

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

    def _screenshot_b64(self, *, full_page: bool = True) -> str:
        """Take screenshot and return base64 encoded image."""
        png = self._page().screenshot(full_page=bool(full_page))
        return base64.b64encode(png).decode("ascii")

    def _screenshot_with_save(
        self,
        action: str,
        full_page: bool = True,
    ) -> Dict[str, Any]:
        """
        Take screenshot, save to disk, and return both base64 and URL.

        Returns:
            Dict with 'image' (base64), 'screenshot_url', 'screenshot_filename'
        """
        page = self._page()
        png_bytes = page.screenshot(full_page=bool(full_page))
        b64_image = base64.b64encode(png_bytes).decode("ascii")

        result = {"image": b64_image}

        # Save to disk if screenshot service is available
        if self.save_screenshots:
            service = _get_screenshot_service()
            if service:
                try:
                    # Run async save in sync context
                    loop = asyncio.new_event_loop()
                    try:
                        save_result = loop.run_until_complete(
                            service.save_screenshot(
                                image_data=png_bytes,
                                action=action,
                                thread_id=self.thread_id,
                                page_url=self._page_info().get("url"),
                            )
                        )
                    finally:
                        loop.close()

                    if save_result.get("url"):
                        result["screenshot_url"] = save_result["url"]
                        result["screenshot_filename"] = save_result.get("filename")
                        logger.debug(f"[sb_browser] Screenshot saved: {save_result['url']}")
                except Exception as e:
                    logger.warning(f"[sb_browser] Failed to save screenshot: {e}")

        return result

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event (synchronous version for tool execution)."""
        if not self.emit_events:
            return

        emitter = _get_event_emitter(self.thread_id)
        if not emitter:
            return

        try:
            # Run async emit in sync context
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(emitter.emit(event_type, data))
            finally:
                loop.close()
        except Exception as e:
            logger.warning(f"[sb_browser] Failed to emit event: {e}")

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


class SbBrowserNavigateInput(BaseModel):
    url: str = Field(min_length=1)
    wait_until: str = Field(default="domcontentloaded", description="domcontentloaded|load|networkidle")
    wait_ms: int = Field(default=1000, ge=0, le=15000)
    full_page: bool = True


class SbBrowserNavigateTool(_SbBrowserTool):
    name: str = "sb_browser_navigate"
    description: str = "Navigate the sandboxed Chromium browser to a URL and return a screenshot."
    args_schema: type[BaseModel] = SbBrowserNavigateInput

    def _run(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        wait_ms: int = 1000,
        full_page: bool = True,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("navigate", {"url": url})

        try:
            page = self._page()
            page.goto(url, wait_until=wait_until, timeout=60000)
            if wait_ms:
                page.wait_for_timeout(int(wait_ms))

            info = self._page_info()
            screenshot = self._screenshot_with_save("navigate", full_page=full_page)

            result = {**info, **screenshot}

            # Emit screenshot event
            self._emit_screenshot(screenshot, "navigate")
            self._emit_tool_result("navigate", result, start_time, success=True)

            return result

        except Exception as e:
            self._emit_tool_result("navigate", {"error": str(e)}, start_time, success=False)
            raise


class SbBrowserClickInput(BaseModel):
    selector: Optional[str] = Field(default=None, description="CSS selector to click")
    text: Optional[str] = Field(default=None, description="Visible text to click (fallback)")
    wait_ms: int = Field(default=800, ge=0, le=15000)
    full_page: bool = True


class SbBrowserClickTool(_SbBrowserTool):
    name: str = "sb_browser_click"
    description: str = "Click an element by CSS selector or visible text (sandbox browser). Returns screenshot."
    args_schema: type[BaseModel] = SbBrowserClickInput

    def _run(
        self,
        selector: Optional[str] = None,
        text: Optional[str] = None,
        wait_ms: int = 800,
        full_page: bool = True,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("click", {"selector": selector, "text": text})

        try:
            page = self._page()
            if selector and selector.strip():
                page.locator(selector.strip()).first.click(timeout=30000)
            elif text and text.strip():
                t = text.strip()
                try:
                    page.get_by_role("link", name=t).first.click(timeout=30000)
                except Exception:
                    try:
                        page.get_by_role("button", name=t).first.click(timeout=30000)
                    except Exception:
                        page.get_by_text(t, exact=False).first.click(timeout=30000)
            else:
                raise ValueError("Either selector or text is required.")

            if wait_ms:
                page.wait_for_timeout(int(wait_ms))

            info = self._page_info()
            screenshot = self._screenshot_with_save("click", full_page=full_page)

            result = {**info, **screenshot}

            self._emit_screenshot(screenshot, "click")
            self._emit_tool_result("click", result, start_time, success=True)

            return result

        except Exception as e:
            self._emit_tool_result("click", {"error": str(e)}, start_time, success=False)
            raise


class SbBrowserTypeInput(BaseModel):
    text: str = Field(min_length=1)
    selector: Optional[str] = Field(default=None, description="CSS selector for an input/textarea; defaults to first input")
    press_enter: bool = False
    wait_ms: int = Field(default=800, ge=0, le=15000)
    full_page: bool = True


class SbBrowserTypeTool(_SbBrowserTool):
    name: str = "sb_browser_type"
    description: str = "Fill an input (by selector or first input) with text. Returns screenshot."
    args_schema: type[BaseModel] = SbBrowserTypeInput

    def _run(
        self,
        text: str,
        selector: Optional[str] = None,
        press_enter: bool = False,
        wait_ms: int = 800,
        full_page: bool = True,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("type", {
            "text": text[:50] + "..." if len(text) > 50 else text,
            "selector": selector,
            "press_enter": press_enter,
        })

        try:
            page = self._page()
            loc = (
                page.locator(selector.strip()).first
                if selector and selector.strip()
                else page.locator("input, textarea, [contenteditable='true']").first
            )
            loc.click(timeout=30000)
            try:
                loc.fill(text)
            except Exception:
                loc.type(text)
            if press_enter:
                page.keyboard.press("Enter")
            if wait_ms:
                page.wait_for_timeout(int(wait_ms))

            info = self._page_info()
            screenshot = self._screenshot_with_save("type", full_page=full_page)

            result = {**info, **screenshot}

            self._emit_screenshot(screenshot, "type")
            self._emit_tool_result("type", result, start_time, success=True)

            return result

        except Exception as e:
            self._emit_tool_result("type", {"error": str(e)}, start_time, success=False)
            raise


class SbBrowserPressInput(BaseModel):
    keys: str = Field(min_length=1, description="e.g. Enter, Control+L, ArrowDown")
    wait_ms: int = Field(default=500, ge=0, le=15000)
    full_page: bool = True


class SbBrowserPressTool(_SbBrowserTool):
    name: str = "sb_browser_press"
    description: str = "Send a keyboard shortcut to the sandbox browser. Returns screenshot."
    args_schema: type[BaseModel] = SbBrowserPressInput

    def _run(self, keys: str, wait_ms: int = 500, full_page: bool = True) -> Dict[str, Any]:
        start_time = self._emit_tool_start("press", {"keys": keys})

        try:
            page = self._page()
            page.keyboard.press(keys)
            if wait_ms:
                page.wait_for_timeout(int(wait_ms))

            info = self._page_info()
            screenshot = self._screenshot_with_save("press", full_page=full_page)

            result = {**info, **screenshot}

            self._emit_screenshot(screenshot, "press")
            self._emit_tool_result("press", result, start_time, success=True)

            return result

        except Exception as e:
            self._emit_tool_result("press", {"error": str(e)}, start_time, success=False)
            raise


class SbBrowserScrollInput(BaseModel):
    amount: int = Field(description="Positive = scroll down, negative = scroll up")
    wait_ms: int = Field(default=500, ge=0, le=15000)
    full_page: bool = True


class SbBrowserScrollTool(_SbBrowserTool):
    name: str = "sb_browser_scroll"
    description: str = "Scroll the sandbox browser page. Returns screenshot."
    args_schema: type[BaseModel] = SbBrowserScrollInput

    def _run(self, amount: int, wait_ms: int = 500, full_page: bool = True) -> Dict[str, Any]:
        start_time = self._emit_tool_start("scroll", {"amount": amount})

        try:
            page = self._page()
            amt = int(amount)
            page.mouse.wheel(0, amt)
            if wait_ms:
                page.wait_for_timeout(int(wait_ms))

            info = self._page_info()
            screenshot = self._screenshot_with_save("scroll", full_page=full_page)

            result = {**info, **screenshot}

            self._emit_screenshot(screenshot, "scroll")
            self._emit_tool_result("scroll", result, start_time, success=True)

            return result

        except Exception as e:
            self._emit_tool_result("scroll", {"error": str(e)}, start_time, success=False)
            raise


class SbBrowserExtractTextInput(BaseModel):
    max_chars: int = Field(default=5000, ge=200, le=40000)


class SbBrowserExtractTextTool(_SbBrowserTool):
    name: str = "sb_browser_extract_text"
    description: str = "Extract visible text from the current sandbox browser page."
    args_schema: type[BaseModel] = SbBrowserExtractTextInput

    def _run(self, max_chars: int = 5000) -> Dict[str, Any]:
        start_time = self._emit_tool_start("extract_text", {"max_chars": max_chars})

        try:
            page = self._page()
            try:
                text = page.inner_text("body")
            except Exception:
                text = page.content()

            info = self._page_info()
            result = {**info, "text": _trim(text, int(max_chars))}

            self._emit_tool_result("extract_text", result, start_time, success=True)

            return result

        except Exception as e:
            self._emit_tool_result("extract_text", {"error": str(e)}, start_time, success=False)
            raise


class SbBrowserScreenshotInput(BaseModel):
    full_page: bool = True


class SbBrowserScreenshotTool(_SbBrowserTool):
    name: str = "sb_browser_screenshot"
    description: str = "Take a screenshot of the current sandbox browser page."
    args_schema: type[BaseModel] = SbBrowserScreenshotInput

    def _run(self, full_page: bool = True) -> Dict[str, Any]:
        start_time = self._emit_tool_start("screenshot", {"full_page": full_page})

        try:
            info = self._page_info()
            screenshot = self._screenshot_with_save("screenshot", full_page=full_page)

            result = {**info, **screenshot}

            self._emit_screenshot(screenshot, "screenshot")
            self._emit_tool_result("screenshot", result, start_time, success=True)

            return result

        except Exception as e:
            self._emit_tool_result("screenshot", {"error": str(e)}, start_time, success=False)
            raise


class SbBrowserResetTool(_SbBrowserTool):
    name: str = "sb_browser_reset"
    description: str = "Close and reset the sandbox browser session (kills the sandbox)."

    def _run(self) -> Dict[str, Any]:
        start_time = self._emit_tool_start("reset", {})

        try:
            sandbox_browser_sessions.reset(self.thread_id)
            result = {"status": "reset", "thread_id": self.thread_id}

            self._emit_tool_result("reset", result, start_time, success=True)

            return result

        except Exception as e:
            self._emit_tool_result("reset", {"error": str(e)}, start_time, success=False)
            raise


def build_sandbox_browser_tools(
    thread_id: str,
    emit_events: bool = True,
    save_screenshots: bool = True,
) -> List[BaseTool]:
    """
    Build sandbox browser tools for a thread.

    Args:
        thread_id: Thread/conversation ID
        emit_events: Whether to emit events for visualization
        save_screenshots: Whether to save screenshots to disk

    Returns:
        List of browser tools
    """
    return [
        SbBrowserNavigateTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
        SbBrowserClickTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
        SbBrowserTypeTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
        SbBrowserPressTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
        SbBrowserScrollTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
        SbBrowserExtractTextTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
        SbBrowserScreenshotTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
        SbBrowserResetTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
    ]
