from __future__ import annotations

import asyncio
import base64
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

    # ------------- helpers -------------
    def _emit(self, event_type: ToolEventType, data: dict):
        try:
            emitter = get_emitter_sync(self.thread_id)
            emitter.emit(event_type, data)
        except Exception:
            pass

    async def _ensure_context(self):
        try:
            from browser_use import Browser as BrowserUseBrowser, BrowserConfig
            from browser_use.browser.context import BrowserContextConfig
            from browser_use.dom.service import DomService
        except Exception as e:  # pragma: no cover - optional dependency
            raise RuntimeError(f"browser-use not installed: {e}")

        if self._browser is None:
            cfg_kwargs = {
                "headless": getattr(settings, "enable_browser_use", False) is False and getattr(settings, "app_env", "dev") != "prod",
                "disable_security": True,
            }
            browser_cfg = getattr(settings, "app_config_object", None)
            if browser_cfg and getattr(browser_cfg, "browser_config", None):
                bc = browser_cfg.browser_config
                if bc.proxy and bc.proxy.server:
                    from browser_use.browser.browser import ProxySettings
                    cfg_kwargs["proxy"] = ProxySettings(
                        server=bc.proxy.server, username=bc.proxy.username, password=bc.proxy.password
                    )
                for attr in ("headless", "disable_security", "extra_chromium_args", "chrome_instance_path", "wss_url", "cdp_url"):
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
            self._context = await self._browser.new_context(context_cfg) if context_cfg else await self._browser.new_context()
            try:
                from browser_use.dom.service import DomService
                self._dom_service = DomService(await self._context.get_current_page())
            except Exception:
                self._dom_service = None
        return self._context

    async def _take_screenshot(self, page) -> Optional[str]:
        try:
            await page.bring_to_front()
            await page.wait_for_load_state()
            img = await page.screenshot(full_page=True, animations="disabled", type="jpeg", quality=85)
            b64 = base64.b64encode(img).decode("utf-8")
            self._emit(ToolEventType.TOOL_SCREENSHOT, {"tool": self.name, "url": page.url, "image": b64})
            return b64
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
                    shot = await self._take_screenshot(page)
                    return {"status": "ok", "url": page.url, "title": await page.title(), "screenshot": shot}

                if action == "go_back":
                    await ctx.go_back()
                    shot = await self._take_screenshot(page)
                    return {"status": "ok", "message": "back", "screenshot": shot}

                if action == "click_element":
                    idx = kwargs.get("index")
                    if idx is None:
                        raise ValueError("index is required for click_element")
                    element = await ctx.get_dom_element_by_index(idx)
                    if not element:
                        raise ValueError(f"Element {idx} not found")
                    await ctx._click_element_node(element)
                    shot = await self._take_screenshot(page)
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
                    return {"status": "ok", "scrolled": direction * amount}

                if action == "scroll_to_text":
                    text = kwargs.get("text") or ""
                    locator = page.get_by_text(text, exact=False)
                    await locator.scroll_into_view_if_needed()
                    return {"status": "ok", "text": text}

                if action == "send_keys":
                    keys = kwargs.get("keys") or ""
                    await page.keyboard.press(keys)
                    return {"status": "ok", "keys": keys}

                if action == "switch_tab":
                    tab_id = kwargs.get("tab_id")
                    await ctx.switch_to_tab(tab_id)
                    await page.wait_for_load_state()
                    return {"status": "ok", "tab": tab_id}

                if action == "open_tab":
                    url = kwargs.get("url")
                    await ctx.create_new_tab(url)
                    return {"status": "ok", "opened": url}

                if action == "close_tab":
                    await ctx.close_current_tab()
                    return {"status": "ok", "closed": True}

                if action == "wait":
                    await asyncio.sleep(kwargs.get("seconds") or 3)
                    return {"status": "ok", "waited": kwargs.get("seconds") or 3}

                if action == "screenshot":
                    shot = await self._take_screenshot(page)
                    return {"status": "ok", "screenshot": shot}

                if action == "web_search":
                    query = kwargs.get("query")
                    if not query:
                        raise ValueError("query required for web_search")
                    url = f"https://www.google.com/search?q={query}"
                    await page.goto(url)
                    await page.wait_for_load_state()
                    shot = await self._take_screenshot(page)
                    return {"status": "ok", "url": page.url, "screenshot": shot}

                if action == "extract_content":
                    goal = kwargs.get("goal") or ""
                    content = await page.content()
                    max_len = getattr(settings.app_config_object.browser_config, "max_content_length", 2000) if getattr(settings, "app_config_object", None) and getattr(settings.app_config_object, "browser_config", None) else 2000
                    return {"status": "ok", "goal": goal, "content": content[: max_len]}

                raise ValueError(f"Unsupported action: {action}")
            except Exception as e:
                self._emit(ToolEventType.TOOL_ERROR, {"tool": self.name, "error": str(e)})
                return {"error": str(e)}


def build_browser_use_tools(thread_id: str) -> list[BaseTool]:
    """Factory to align with build_agent_tools."""
    return [BrowserUseTool(thread_id=thread_id)]
