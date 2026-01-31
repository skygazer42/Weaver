from __future__ import annotations

import asyncio
import base64
import hashlib
import time
from typing import Any, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from agent.core.events import ToolEventType, get_emitter_sync
from common.config import settings


class BrowserUseInput(BaseModel):
    action: str = Field(..., description="Browser action to perform")
    url: Optional[str] = None
    index: Optional[int] = None
    text: Optional[str] = None
    scroll_amount: Optional[int] = None
    tab_id: Optional[int] = None
    query: Optional[str] = None
    goal: Optional[str] = None
    keys: Optional[str] = None
    seconds: Optional[int] = None


class BrowserUseTool(BaseTool):
    """
    Playwright/browser-use based automation tool with event emission.

    This is a light-weight adaptation of OpenManus' BrowserUseTool. It keeps
    the same action contract but trims the feature set to the common actions
    used in Weaver (navigate, click, input, scroll, screenshot).
    """

    name: str = "browser_use"
    description: str = (
        "Full Chromium browser automation powered by browser-use. "
        "Supports navigate, click, input, scroll, tab switching and screenshots."
    )
    args_schema: type[BaseModel] = BrowserUseInput
    thread_id: str = "default"

    def __init__(self, thread_id: str = "default", **kwargs: Any):
        super().__init__(**kwargs)
        self.thread_id = thread_id
        self._browser = None
        self._context = None
        self._dom_service = None
        self._lock = asyncio.Lock()
        self._last_screenshot_at = 0.0
        self._last_screenshot_hash: Optional[str] = None
        self._scroll_accum_px = 0
        self._arrow_press_accum = 0

    # ------------- helpers -------------
    def _emit(self, event_type: ToolEventType, data: dict):
        try:
            emitter = get_emitter_sync(self.thread_id)
            emitter.emit_sync(event_type, data)
        except Exception:
            pass

    async def _ensure_context(self):
        from browser_use import Browser as BrowserUseBrowser
        from browser_use import BrowserConfig
        from browser_use.browser.context import BrowserContextConfig
        from browser_use.dom.service import DomService

        if self._browser is None:
            cfg_kwargs = {
                "headless": getattr(settings, "enable_browser_use", False) is False
                and getattr(settings, "app_env", "dev") != "prod",
                "disable_security": True,
            }
            browser_cfg = getattr(settings, "app_config_object", None)
            if browser_cfg and getattr(browser_cfg, "browser_config", None):
                bc = browser_cfg.browser_config
                if bc.proxy and bc.proxy.server:
                    from browser_use.browser.browser import ProxySettings

                    cfg_kwargs["proxy"] = ProxySettings(
                        server=bc.proxy.server,
                        username=bc.proxy.username,
                        password=bc.proxy.password,
                    )
                for attr in (
                    "headless",
                    "disable_security",
                    "extra_chromium_args",
                    "chrome_instance_path",
                    "wss_url",
                    "cdp_url",
                ):
                    val = getattr(bc, attr, None)
                    if val is not None:
                        cfg_kwargs[attr] = val

            self._browser = BrowserUseBrowser(BrowserConfig(**cfg_kwargs))

        if self._context is None:
            context_cfg = None
            try:
                from browser_use.browser.context import BrowserContextConfig

                context_cfg = BrowserContextConfig()
            except Exception:
                context_cfg = None
            self._context = (
                await self._browser.new_context(context_cfg)
                if context_cfg
                else await self._browser.new_context()
            )
            try:
                from browser_use.dom.service import DomService

                self._dom_service = DomService(await self._context.get_current_page())
            except Exception:
                self._dom_service = None
        return self._context

    async def _take_screenshot(
        self,
        page,
        *,
        action: str = "screenshot",
        full_page: bool = False,
        min_interval_ms: int = 0,
        dedupe: bool = True,
    ) -> Optional[str]:
        try:
            now = time.monotonic()
            if min_interval_ms > 0 and (now - self._last_screenshot_at) < (
                min_interval_ms / 1000.0
            ):
                return None
            await page.bring_to_front()
            await page.wait_for_load_state()
            try:
                img = await page.screenshot(
                    full_page=bool(full_page),
                    animations="disabled",
                    caret="hide",
                    type="jpeg",
                    quality=85,
                )
            except TypeError:
                # Backwards-compat: older Playwright builds may not support animations/caret options.
                img = await page.screenshot(full_page=bool(full_page), type="jpeg", quality=85)

            img_hash = hashlib.sha256(img).hexdigest()
            # We already paid the cost of capturing; record the time so we don't
            # spam follow-up captures on rapid-fire actions.
            self._last_screenshot_at = now
            if dedupe and self._last_screenshot_hash == img_hash:
                return None

            screenshot_url: Optional[str] = None
            screenshot_filename: Optional[str] = None
            mime_type: str = "image/jpeg"
            b64: Optional[str] = None

            # Best-effort: persist screenshot so SSE stays lightweight and tool
            # output doesn't explode the token budget.
            try:
                from tools.io.screenshot_service import get_screenshot_service

                save_result = get_screenshot_service().save_screenshot_sync(
                    image_data=img,
                    action=f"{self.name}_{action}",
                    thread_id=self.thread_id,
                    page_url=page.url,
                )
                screenshot_url = save_result.get("url")
                screenshot_filename = save_result.get("filename")
                mime_type = save_result.get("mime_type") or mime_type
            except Exception:
                screenshot_url = None

            # Only include base64 when we couldn't persist to disk.
            if not screenshot_url:
                b64 = base64.b64encode(img).decode("utf-8")

            self._emit(
                ToolEventType.TOOL_SCREENSHOT,
                {
                    "tool": self.name,
                    "action": action,
                    "url": screenshot_url,
                    "filename": screenshot_filename,
                    "page_url": page.url,
                    "image": b64,
                    "mime_type": mime_type,
                },
            )
            self._last_screenshot_hash = img_hash
            # Keep tool outputs small: return URL when available, else omit (SSE may still carry base64).
            return screenshot_url
        except Exception:
            return None

    # ------------- sync entrypoint -------------
    def _run(self, **kwargs: Any) -> Any:
        return asyncio.run(self._arun(**kwargs))

    async def _arun(self, **kwargs: Any) -> Any:
        action = kwargs.get("action")
        self._emit(ToolEventType.TOOL_START, {"tool": self.name, "args": kwargs})
        async with self._lock:
            try:
                ctx = await self._ensure_context()
                page = await ctx.get_current_page()

                if action == "go_to_url":
                    url = kwargs.get("url")
                    if not url:
                        raise ValueError("url is required for go_to_url")
                    await page.goto(url)
                    await page.wait_for_load_state()
                    shot = await self._take_screenshot(page, action="navigate")
                    self._scroll_accum_px = 0
                    self._arrow_press_accum = 0
                    return {
                        "status": "ok",
                        "url": page.url,
                        "title": await page.title(),
                        "screenshot": shot,
                    }

                if action == "go_back":
                    await ctx.go_back()
                    shot = await self._take_screenshot(page, action="back")
                    self._scroll_accum_px = 0
                    self._arrow_press_accum = 0
                    return {"status": "ok", "message": "back", "screenshot": shot}

                if action == "click_element":
                    idx = kwargs.get("index")
                    if idx is None:
                        raise ValueError("index is required for click_element")
                    element = await ctx.get_dom_element_by_index(idx)
                    if not element:
                        raise ValueError(f"Element {idx} not found")
                    await ctx._click_element_node(element)
                    shot = await self._take_screenshot(page, action="click")
                    self._scroll_accum_px = 0
                    self._arrow_press_accum = 0
                    return {"status": "ok", "clicked": idx, "screenshot": shot}

                if action == "input_text":
                    idx = kwargs.get("index")
                    text = kwargs.get("text")
                    if idx is None or text is None:
                        raise ValueError("index and text are required for input_text")
                    element = await ctx.get_dom_element_by_index(idx)
                    await ctx._input_text_element_node(element, text)
                    return {"status": "ok", "input": text}

                if action in ("scroll_down", "scroll_up"):
                    amount = kwargs.get("scroll_amount")
                    direction = 1 if action == "scroll_down" else -1
                    if amount is None:
                        amount = ctx.config.browser_window_size.get("height", 800)
                    await ctx.execute_javascript(f"window.scrollBy(0, {direction * amount});")
                    page = await ctx.get_current_page()
                    viewport_h = (
                        (page.viewport_size or {}).get("height")
                        if getattr(page, "viewport_size", None)
                        else None
                    )
                    threshold = int((int(viewport_h) if viewport_h else 800) * 0.75)
                    self._scroll_accum_px += direction * int(amount)
                    shot = None
                    if abs(self._scroll_accum_px) >= threshold:
                        shot = await self._take_screenshot(page, action=action, min_interval_ms=800)
                        self._scroll_accum_px = 0
                    return {"status": "ok", "scrolled": direction * amount, "screenshot": shot}

                if action == "scroll_to_text":
                    text = kwargs.get("text") or ""
                    locator = page.get_by_text(text, exact=False)
                    await locator.scroll_into_view_if_needed()
                    page = await ctx.get_current_page()
                    shot = await self._take_screenshot(page, action="scroll_to_text")
                    self._scroll_accum_px = 0
                    return {"status": "ok", "text": text, "screenshot": shot}

                if action == "send_keys":
                    keys = kwargs.get("keys") or ""
                    await page.keyboard.press(keys)
                    page = await ctx.get_current_page()
                    keys_upper = keys.upper().replace(" ", "")
                    meaningful_keys = ("ENTER", "PAGEDOWN", "PAGEUP", "HOME", "END", "SPACE")
                    arrow_keys = ("ARROWDOWN", "ARROWUP")
                    shot = None
                    if any(token in keys_upper for token in meaningful_keys):
                        self._arrow_press_accum = 0
                        self._scroll_accum_px = 0
                        shot = await self._take_screenshot(
                            page, action=f"keys:{keys}", min_interval_ms=700
                        )
                    elif any(token in keys_upper for token in arrow_keys):
                        self._arrow_press_accum += 1
                        if self._arrow_press_accum >= 3:
                            shot = await self._take_screenshot(
                                page, action=f"keys:{keys}", min_interval_ms=700
                            )
                            self._arrow_press_accum = 0
                    else:
                        self._arrow_press_accum = 0
                    return {"status": "ok", "keys": keys, "screenshot": shot}

                if action == "switch_tab":
                    tab_id = kwargs.get("tab_id")
                    await ctx.switch_to_tab(tab_id)
                    page = await ctx.get_current_page()
                    await page.wait_for_load_state()
                    shot = await self._take_screenshot(page, action="switch_tab")
                    self._scroll_accum_px = 0
                    self._arrow_press_accum = 0
                    return {"status": "ok", "tab": tab_id, "screenshot": shot}

                if action == "open_tab":
                    url = kwargs.get("url")
                    await ctx.create_new_tab(url)
                    page = await ctx.get_current_page()
                    await page.wait_for_load_state()
                    shot = await self._take_screenshot(page, action="open_tab")
                    self._scroll_accum_px = 0
                    self._arrow_press_accum = 0
                    return {"status": "ok", "opened": url, "screenshot": shot}

                if action == "close_tab":
                    await ctx.close_current_tab()
                    page = await ctx.get_current_page()
                    await page.wait_for_load_state()
                    shot = await self._take_screenshot(page, action="close_tab")
                    self._scroll_accum_px = 0
                    self._arrow_press_accum = 0
                    return {"status": "ok", "closed": True, "screenshot": shot}

                if action == "wait":
                    await asyncio.sleep(kwargs.get("seconds") or 3)
                    page = await ctx.get_current_page()
                    seconds = kwargs.get("seconds") or 3
                    shot = (
                        await self._take_screenshot(page, action="wait", min_interval_ms=2000)
                        if int(seconds) >= 2
                        else None
                    )
                    return {"status": "ok", "waited": seconds, "screenshot": shot}

                if action == "screenshot":
                    shot = await self._take_screenshot(page, action="screenshot", full_page=True)
                    return {"status": "ok", "screenshot": shot}

                if action == "web_search":
                    query = kwargs.get("query")
                    if not query:
                        raise ValueError("query required for web_search")
                    url = f"https://www.google.com/search?q={query}"
                    await page.goto(url)
                    await page.wait_for_load_state()
                    shot = await self._take_screenshot(page, action="search")
                    return {"status": "ok", "url": page.url, "screenshot": shot}

                if action == "extract_content":
                    goal = kwargs.get("goal") or ""
                    content = await page.content()
                    max_len = (
                        getattr(
                            settings.app_config_object.browser_config, "max_content_length", 2000
                        )
                        if getattr(settings, "app_config_object", None)
                        and getattr(settings.app_config_object, "browser_config", None)
                        else 2000
                    )
                    return {"status": "ok", "goal": goal, "content": content[:max_len]}

                raise ValueError(f"Unsupported action: {action}")
            except Exception as e:
                self._emit(ToolEventType.TOOL_ERROR, {"tool": self.name, "error": str(e)})
                return {"error": str(e)}


def build_browser_use_tools(thread_id: str) -> list[BaseTool]:
    """Factory to align with build_agent_tools."""
    return [BrowserUseTool(thread_id=thread_id)]
