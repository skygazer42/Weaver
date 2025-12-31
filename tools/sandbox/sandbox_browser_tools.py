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
import hashlib
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .sandbox_browser_session import sandbox_browser_sessions

logger = logging.getLogger(__name__)

# Per-thread state to keep screenshots human-like:
# - De-dupe identical screenshots across tool calls
# - Accumulate small scroll/arrow interactions into meaningful captures
_SB_THREAD_STATE: Dict[str, Dict[str, Any]] = {}


def _get_thread_state(thread_id: str) -> Dict[str, Any]:
    tid = (thread_id or "").strip() or "default"
    state = _SB_THREAD_STATE.get(tid)
    if state is None:
        state = {
            "last_hash": None,
            "last_url": None,
            "last_filename": None,
            "last_mime_type": None,
            "scroll_accum": 0,
            "arrow_accum": 0,
        }
        _SB_THREAD_STATE[tid] = state
    return state


def _trim(text: str, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _get_event_emitter(thread_id: str):
    """Get event emitter for a thread (lazy import to avoid circular deps)."""
    from agent.core.events import get_emitter_sync

    return get_emitter_sync(thread_id)


def _get_screenshot_service():
    """Get screenshot service (lazy import)."""
    from tools.io.screenshot_service import get_screenshot_service

    return get_screenshot_service()


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

    def _screenshot_bytes(self, *, full_page: bool) -> bytes:
        page = self._page()
        try:
            return page.screenshot(full_page=bool(full_page), animations="disabled", caret="hide")
        except TypeError:
            # Backwards-compat: older Playwright builds may not support animations/caret options.
            return page.screenshot(full_page=bool(full_page))

    def _screenshot_b64(self, *, full_page: bool = True) -> str:
        """Take screenshot and return base64 encoded image."""
        png = self._screenshot_bytes(full_page=full_page)
        return base64.b64encode(png).decode("ascii")

    def _screenshot_with_save(
        self,
        action: str,
        full_page: bool = True,
    ) -> Tuple[Dict[str, Any], str]:
        """
        Take screenshot, save to disk, and return URL (base64 fallback).

        Returns:
            Dict with 'screenshot_url' (preferred) and 'image' (base64 fallback)
        """
        png_bytes = self._screenshot_bytes(full_page=full_page)
        image_hash = hashlib.sha256(png_bytes).hexdigest()

        # If the view didn't change, don't generate a new file; reuse the last URL.
        state = _get_thread_state(self.thread_id)
        if state.get("last_hash") == image_hash and state.get("last_url"):
            return (
                {
                    "screenshot_url": state.get("last_url"),
                    "screenshot_filename": state.get("last_filename"),
                    "mime_type": state.get("last_mime_type") or "image/png",
                },
                image_hash,
            )

        result: Dict[str, Any] = {"mime_type": "image/png"}

        # Save to disk if screenshot service is available
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
                        logger.debug(f"[sb_browser] Screenshot saved: {save_result['url']}")
                except Exception as e:
                    logger.warning(f"[sb_browser] Failed to save screenshot: {e}")

        # Only include base64 when we couldn't persist to disk.
        if not result.get("screenshot_url"):
            result["image"] = base64.b64encode(png_bytes).decode("ascii")

        return result, image_hash

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event (synchronous version for tool execution)."""
        if not self.emit_events:
            return

        emitter = _get_event_emitter(self.thread_id)
        if not emitter:
            return

        try:
            # Use synchronous emit method to avoid event loop conflicts
            emitter.emit_sync(event_type, data)
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

    def _emit_progress(self, action: str, info: str):
        self._emit_event("tool_progress", {
            "tool": self.name,
            "action": action,
            "info": info,
            "thread_id": self.thread_id,
        })

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

    def _emit_screenshot(
        self,
        screenshot_data: Dict[str, Any],
        action: str,
        *,
        image_hash: Optional[str] = None,
    ) -> None:
        """Emit screenshot event - supports both URL and base64 image."""
        url = screenshot_data.get("screenshot_url")
        image = screenshot_data.get("image")
        mime_type = screenshot_data.get("mime_type")

        # Emit if we have either URL or base64 image
        if not (url or image):
            return

        # De-dupe identical screenshots across all sb_browser_* tools in the same thread.
        state = _get_thread_state(self.thread_id)
        if image_hash and state.get("last_hash") == image_hash:
            # If we previously couldn't persist (no URL) but now we can, record it
            # so future duplicates can reuse the saved file.
            if url and not state.get("last_url"):
                state["last_url"] = url
                state["last_filename"] = screenshot_data.get("screenshot_filename")
                state["last_mime_type"] = mime_type
            return

        self._emit_event("tool_screenshot", {
            "tool": self.name,
            "action": action,
            "url": url,
            # Keep stream light when the image is accessible by URL.
            "image": image if not url else None,
            "filename": screenshot_data.get("screenshot_filename"),
            "mime_type": mime_type,
            "page_url": self._page_info().get("url"),
        })

        if image_hash:
            state["last_hash"] = image_hash
            state["last_url"] = url
            state["last_filename"] = screenshot_data.get("screenshot_filename")
            state["last_mime_type"] = mime_type


class SbBrowserNavigateInput(BaseModel):
    url: str = Field(min_length=1)
    wait_until: str = Field(default="domcontentloaded", description="domcontentloaded|load|networkidle")
    wait_ms: int = Field(default=1000, ge=0, le=15000)
    full_page: bool = False


class SbBrowserNavigateTool(_SbBrowserTool):
    name: str = "sb_browser_navigate"
    description: str = "Navigate the sandboxed Chromium browser to a URL and return a screenshot."
    args_schema: type[BaseModel] = SbBrowserNavigateInput

    def _run(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        wait_ms: int = 1000,
        full_page: bool = False,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("navigate", {"url": url})
        self._emit_progress("navigate", f"goto {url}")
        state = _get_thread_state(self.thread_id)
        state["scroll_accum"] = 0
        state["arrow_accum"] = 0

        try:
            page = self._page()
            page.goto(url, wait_until=wait_until, timeout=60000)
            if wait_ms:
                page.wait_for_timeout(int(wait_ms))
            self._emit_progress("navigate", "page_loaded")

            info = self._page_info()
            screenshot, screenshot_hash = self._screenshot_with_save("navigate", full_page=full_page)
            self._emit_progress("navigate", "screenshot_captured")

            result = {**info, **screenshot}

            # Emit screenshot event
            self._emit_screenshot(screenshot, "navigate", image_hash=screenshot_hash)
            self._emit_tool_result("navigate", result, start_time, success=True)

            return result

        except Exception as e:
            self._emit_tool_result("navigate", {"error": str(e)}, start_time, success=False)
            raise


class SbBrowserClickInput(BaseModel):
    selector: Optional[str] = Field(default=None, description="CSS selector to click")
    text: Optional[str] = Field(default=None, description="Visible text to click (fallback)")
    wait_ms: int = Field(default=800, ge=0, le=15000)
    full_page: bool = False


class SbBrowserClickTool(_SbBrowserTool):
    name: str = "sb_browser_click"
    description: str = "Click an element by CSS selector or visible text (sandbox browser). Returns screenshot."
    args_schema: type[BaseModel] = SbBrowserClickInput

    def _run(
        self,
        selector: Optional[str] = None,
        text: Optional[str] = None,
        wait_ms: int = 800,
        full_page: bool = False,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("click", {"selector": selector, "text": text})
        self._emit_progress("click", selector or text or "")

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
            self._emit_progress("click", "after_click_wait")

            info = self._page_info()
            state = _get_thread_state(self.thread_id)
            state["scroll_accum"] = 0
            state["arrow_accum"] = 0
            screenshot, screenshot_hash = self._screenshot_with_save("click", full_page=full_page)

            result = {**info, **screenshot}

            self._emit_screenshot(screenshot, "click", image_hash=screenshot_hash)
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
    full_page: bool = False


class SbBrowserTypeTool(_SbBrowserTool):
    name: str = "sb_browser_type"
    description: str = (
        "Fill an input (by selector or first input) with text. "
        "Emits/returns a screenshot when submitting (press_enter=true)."
    )
    args_schema: type[BaseModel] = SbBrowserTypeInput

    def _run(
        self,
        text: str,
        selector: Optional[str] = None,
        press_enter: bool = False,
        wait_ms: int = 800,
        full_page: bool = False,
    ) -> Dict[str, Any]:
        start_time = self._emit_tool_start("type", {
            "text": text[:50] + "..." if len(text) > 50 else text,
            "selector": selector,
            "press_enter": press_enter,
        })
        self._emit_progress("type", selector or "first_input")

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
            self._emit_progress("type", "after_type_wait")

            info = self._page_info()
            screenshot: Dict[str, Any] = {}
            screenshot_hash: Optional[str] = None
            screenshot_action = "submit" if press_enter else "type"
            if press_enter:
                state = _get_thread_state(self.thread_id)
                state["scroll_accum"] = 0
                state["arrow_accum"] = 0
                screenshot, screenshot_hash = self._screenshot_with_save("type", full_page=full_page)

            result = {**info, **screenshot}

            if screenshot:
                self._emit_screenshot(screenshot, screenshot_action, image_hash=screenshot_hash)
            self._emit_tool_result("type", result, start_time, success=True)

            return result

        except Exception as e:
            self._emit_tool_result("type", {"error": str(e)}, start_time, success=False)
            raise


class SbBrowserPressInput(BaseModel):
    keys: str = Field(min_length=1, description="e.g. Enter, Control+L, ArrowDown")
    wait_ms: int = Field(default=500, ge=0, le=15000)
    full_page: bool = False


class SbBrowserPressTool(_SbBrowserTool):
    name: str = "sb_browser_press"
    description: str = (
        "Send a keyboard shortcut to the sandbox browser. "
        "Emits/returns a screenshot for view-changing keys (Enter/PageUp/PageDown/Home/End/Space) "
        "and after a few ArrowUp/ArrowDown steps."
    )
    args_schema: type[BaseModel] = SbBrowserPressInput

    def _run(self, keys: str, wait_ms: int = 500, full_page: bool = False) -> Dict[str, Any]:
        start_time = self._emit_tool_start("press", {"keys": keys})
        self._emit_progress("press", keys)

        try:
            page = self._page()
            page.keyboard.press(keys)
            if wait_ms:
                page.wait_for_timeout(int(wait_ms))
            self._emit_progress("press", "after_press_wait")

            info = self._page_info()
            keys_upper = (keys or "").upper().replace(" ", "")
            meaningful = any(token in keys_upper for token in ("ENTER", "PAGEDOWN", "PAGEUP", "HOME", "END", "SPACE"))
            screenshot: Dict[str, Any] = {}
            screenshot_hash: Optional[str] = None
            state = _get_thread_state(self.thread_id)
            if meaningful:
                state["arrow_accum"] = 0
                state["scroll_accum"] = 0
                screenshot, screenshot_hash = self._screenshot_with_save("press", full_page=full_page)
            elif any(token in keys_upper for token in ("ARROWDOWN", "ARROWUP")):
                state["arrow_accum"] = int(state.get("arrow_accum") or 0) + 1
                if state["arrow_accum"] >= 3:
                    screenshot, screenshot_hash = self._screenshot_with_save("press", full_page=full_page)
                    state["arrow_accum"] = 0
            else:
                state["arrow_accum"] = 0

            result = {**info, **screenshot}

            if screenshot:
                self._emit_screenshot(screenshot, f"press:{keys}", image_hash=screenshot_hash)
            self._emit_tool_result("press", result, start_time, success=True)

            return result

        except Exception as e:
            self._emit_tool_result("press", {"error": str(e)}, start_time, success=False)
            raise


class SbBrowserScrollInput(BaseModel):
    amount: int = Field(description="Positive = scroll down, negative = scroll up")
    wait_ms: int = Field(default=500, ge=0, le=15000)
    full_page: bool = False


class SbBrowserScrollTool(_SbBrowserTool):
    name: str = "sb_browser_scroll"
    description: str = (
        "Scroll the sandbox browser page. "
        "Emits/returns a screenshot when the scroll is significant (about a page)."
    )
    args_schema: type[BaseModel] = SbBrowserScrollInput

    def _run(self, amount: int, wait_ms: int = 500, full_page: bool = False) -> Dict[str, Any]:
        start_time = self._emit_tool_start("scroll", {"amount": amount})
        self._emit_progress("scroll", str(amount))

        try:
            page = self._page()
            amt = int(amount)
            page.mouse.wheel(0, amt)
            if wait_ms:
                page.wait_for_timeout(int(wait_ms))
            self._emit_progress("scroll", "after_scroll_wait")

            info = self._page_info()
            viewport_h = (page.viewport_size or {}).get("height") if getattr(page, "viewport_size", None) else None
            threshold = int((int(viewport_h) if viewport_h else 800) * 0.75)
            screenshot: Dict[str, Any] = {}
            screenshot_hash: Optional[str] = None
            state = _get_thread_state(self.thread_id)
            state["scroll_accum"] = int(state.get("scroll_accum") or 0) + amt
            if abs(int(state["scroll_accum"])) >= threshold:
                screenshot, screenshot_hash = self._screenshot_with_save("scroll", full_page=full_page)
                state["scroll_accum"] = 0

            result = {**info, **screenshot}

            if screenshot:
                self._emit_screenshot(screenshot, "scroll", image_hash=screenshot_hash)
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
        self._emit_progress("extract_text", f"max_chars={max_chars}")

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
    full_page: bool = False


class SbBrowserScreenshotTool(_SbBrowserTool):
    name: str = "sb_browser_screenshot"
    description: str = "Take a screenshot of the current sandbox browser page."
    args_schema: type[BaseModel] = SbBrowserScreenshotInput

    def _run(self, full_page: bool = False) -> Dict[str, Any]:
        start_time = self._emit_tool_start("screenshot", {"full_page": full_page})
        self._emit_progress("screenshot", "capturing")

        try:
            info = self._page_info()
            screenshot, screenshot_hash = self._screenshot_with_save("screenshot", full_page=full_page)

            result = {**info, **screenshot}

            self._emit_screenshot(screenshot, "screenshot", image_hash=screenshot_hash)
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
        self._emit_progress("reset", "closing session")

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
