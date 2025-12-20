from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .sandbox_browser_session import sandbox_browser_sessions


def _trim(text: str, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


class _SbBrowserTool(BaseTool):
    thread_id: str = "default"

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
        png = self._page().screenshot(full_page=bool(full_page))
        return base64.b64encode(png).decode("ascii")


class SbBrowserNavigateInput(BaseModel):
    url: str = Field(min_length=1)
    wait_until: str = Field(default="domcontentloaded", description="domcontentloaded|load|networkidle")
    wait_ms: int = Field(default=1000, ge=0, le=15000)
    full_page: bool = True


class SbBrowserNavigateTool(_SbBrowserTool):
    name: str = "sb_browser_navigate"
    description: str = "Navigate the sandboxed Chromium browser to a URL and return a screenshot."
    args_schema: type[BaseModel] = SbBrowserNavigateInput

    def _run(self, url: str, wait_until: str = "domcontentloaded", wait_ms: int = 1000, full_page: bool = True) -> Dict[str, Any]:
        page = self._page()
        page.goto(url, wait_until=wait_until, timeout=60000)
        if wait_ms:
            page.wait_for_timeout(int(wait_ms))
        info = self._page_info()
        return {
            **info,
            "image": self._screenshot_b64(full_page=full_page),
        }


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
        page = self._page()
        if selector and selector.strip():
            page.locator(selector.strip()).first.click(timeout=30000)
        elif text and text.strip():
            # Prefer role-based locators when possible, fallback to text.
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
        return {**info, "image": self._screenshot_b64(full_page=full_page)}


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
        page = self._page()
        loc = page.locator(selector.strip()).first if selector and selector.strip() else page.locator("input, textarea, [contenteditable='true']").first
        loc.click(timeout=30000)
        # Use fill when available; for contenteditable, fall back to type.
        try:
            loc.fill(text)
        except Exception:
            loc.type(text)
        if press_enter:
            page.keyboard.press("Enter")
        if wait_ms:
            page.wait_for_timeout(int(wait_ms))
        info = self._page_info()
        return {**info, "image": self._screenshot_b64(full_page=full_page)}


class SbBrowserPressInput(BaseModel):
    keys: str = Field(min_length=1, description="e.g. Enter, Control+L, ArrowDown")
    wait_ms: int = Field(default=500, ge=0, le=15000)
    full_page: bool = True


class SbBrowserPressTool(_SbBrowserTool):
    name: str = "sb_browser_press"
    description: str = "Send a keyboard shortcut to the sandbox browser. Returns screenshot."
    args_schema: type[BaseModel] = SbBrowserPressInput

    def _run(self, keys: str, wait_ms: int = 500, full_page: bool = True) -> Dict[str, Any]:
        page = self._page()
        page.keyboard.press(keys)
        if wait_ms:
            page.wait_for_timeout(int(wait_ms))
        info = self._page_info()
        return {**info, "image": self._screenshot_b64(full_page=full_page)}


class SbBrowserScrollInput(BaseModel):
    amount: int = Field(description="Positive = scroll down, negative = scroll up")
    wait_ms: int = Field(default=500, ge=0, le=15000)
    full_page: bool = True


class SbBrowserScrollTool(_SbBrowserTool):
    name: str = "sb_browser_scroll"
    description: str = "Scroll the sandbox browser page. Returns screenshot."
    args_schema: type[BaseModel] = SbBrowserScrollInput

    def _run(self, amount: int, wait_ms: int = 500, full_page: bool = True) -> Dict[str, Any]:
        page = self._page()
        amt = int(amount)
        page.mouse.wheel(0, amt)
        if wait_ms:
            page.wait_for_timeout(int(wait_ms))
        info = self._page_info()
        return {**info, "image": self._screenshot_b64(full_page=full_page)}


class SbBrowserExtractTextInput(BaseModel):
    max_chars: int = Field(default=5000, ge=200, le=40000)


class SbBrowserExtractTextTool(_SbBrowserTool):
    name: str = "sb_browser_extract_text"
    description: str = "Extract visible text from the current sandbox browser page."
    args_schema: type[BaseModel] = SbBrowserExtractTextInput

    def _run(self, max_chars: int = 5000) -> Dict[str, Any]:
        page = self._page()
        try:
            text = page.inner_text("body")
        except Exception:
            text = page.content()
        info = self._page_info()
        return {**info, "text": _trim(text, int(max_chars))}


class SbBrowserScreenshotInput(BaseModel):
    full_page: bool = True


class SbBrowserScreenshotTool(_SbBrowserTool):
    name: str = "sb_browser_screenshot"
    description: str = "Take a screenshot of the current sandbox browser page."
    args_schema: type[BaseModel] = SbBrowserScreenshotInput

    def _run(self, full_page: bool = True) -> Dict[str, Any]:
        info = self._page_info()
        return {**info, "image": self._screenshot_b64(full_page=full_page)}


class SbBrowserResetTool(_SbBrowserTool):
    name: str = "sb_browser_reset"
    description: str = "Close and reset the sandbox browser session (kills the sandbox)."

    def _run(self) -> Dict[str, Any]:
        sandbox_browser_sessions.reset(self.thread_id)
        return {"status": "reset", "thread_id": self.thread_id}


def build_sandbox_browser_tools(thread_id: str) -> List[BaseTool]:
    return [
        SbBrowserNavigateTool(thread_id=thread_id),
        SbBrowserClickTool(thread_id=thread_id),
        SbBrowserTypeTool(thread_id=thread_id),
        SbBrowserPressTool(thread_id=thread_id),
        SbBrowserScrollTool(thread_id=thread_id),
        SbBrowserExtractTextTool(thread_id=thread_id),
        SbBrowserScreenshotTool(thread_id=thread_id),
        SbBrowserResetTool(thread_id=thread_id),
    ]
