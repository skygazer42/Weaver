"""
Computer Use Tool for Desktop Automation.

This tool provides desktop automation capabilities for AI agents, allowing:
- Mouse movement and clicking
- Keyboard input and shortcuts
- Screenshots for visual feedback
- Screen information

Similar to Manus's computer_use_tool.py but adapted for Weaver's architecture.
Uses pyautogui for cross-platform desktop automation.

Usage:
    from tools.automation.computer_use_tool import build_computer_use_tools

    tools = build_computer_use_tools(thread_id="thread_123")

Requirements:
    pip install pyautogui pillow
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Supported keyboard keys
KEYBOARD_KEYS = [
    # Letters
    'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm',
    'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
    # Numbers
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
    # Special keys
    'space', 'enter', 'tab', 'escape', 'backspace', 'delete',
    'shift', 'ctrl', 'alt', 'win', 'command',
    # Arrow keys
    'left', 'right', 'up', 'down',
    # Navigation
    'home', 'end', 'pageup', 'pagedown', 'insert',
    # Function keys
    'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12',
    # Lock keys
    'capslock', 'numlock', 'scrolllock', 'printscreen',
]

# Check if pyautogui is available
try:
    import pyautogui
    pyautogui.FAILSAFE = True  # Move mouse to corner to abort
    pyautogui.PAUSE = 0.1  # Small pause between actions
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    logger.warning("[computer_use] pyautogui not installed. Run: pip install pyautogui")


def _get_event_emitter(thread_id: str):
    """Get event emitter for a thread."""
    try:
        from agent.core.events import get_emitter_sync
        return get_emitter_sync(thread_id)
    except ImportError:
        return None


def _get_screenshot_service():
    """Get screenshot service."""
    try:
        from tools.io.screenshot_service import get_screenshot_service
        return get_screenshot_service()
    except ImportError:
        return None


class _ComputerUseTool(BaseTool):
    """Base class for computer use tools with event emission and screenshots."""

    thread_id: str = "default"
    emit_events: bool = True
    save_screenshots: bool = True

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event for visualization."""
        if not self.emit_events:
            return

        emitter = _get_event_emitter(self.thread_id)
        if not emitter:
            return

        try:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(emitter.emit(event_type, data))
            finally:
                loop.close()
        except Exception as e:
            logger.warning(f"[computer_use] Failed to emit event: {e}")

    def _emit_tool_start(self, action: str, args: Dict[str, Any]) -> float:
        """Emit tool start event."""
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
        })

    def _take_screenshot(self, action: str) -> Dict[str, Any]:
        """Take a screenshot and optionally save it."""
        if not PYAUTOGUI_AVAILABLE:
            return {"error": "pyautogui not available"}

        try:
            # Take screenshot
            screenshot = pyautogui.screenshot()

            # Convert to bytes
            buffer = io.BytesIO()
            screenshot.save(buffer, format="PNG")
            png_bytes = buffer.getvalue()

            # Base64 encode
            b64_image = base64.b64encode(png_bytes).decode("ascii")

            result = {"image": b64_image}

            # Save to disk if service available
            if self.save_screenshots:
                service = _get_screenshot_service()
                if service:
                    try:
                        loop = asyncio.new_event_loop()
                        try:
                            save_result = loop.run_until_complete(
                                service.save_screenshot(
                                    image_data=png_bytes,
                                    action=f"computer_{action}",
                                    thread_id=self.thread_id,
                                )
                            )
                        finally:
                            loop.close()

                        if save_result.get("url"):
                            result["screenshot_url"] = save_result["url"]
                            result["screenshot_filename"] = save_result.get("filename")

                            # Emit screenshot event
                            self._emit_event("tool_screenshot", {
                                "tool": self.name,
                                "action": action,
                                "url": save_result["url"],
                                "filename": save_result.get("filename"),
                            })
                    except Exception as e:
                        logger.warning(f"[computer_use] Failed to save screenshot: {e}")

            return result

        except Exception as e:
            logger.error(f"[computer_use] Screenshot failed: {e}")
            return {"error": str(e)}

    def _get_screen_size(self) -> Tuple[int, int]:
        """Get screen dimensions."""
        if PYAUTOGUI_AVAILABLE:
            return pyautogui.size()
        return (1920, 1080)  # Default


class MoveMouseInput(BaseModel):
    """Input for moving mouse."""
    x: int = Field(description="X coordinate (pixels from left)")
    y: int = Field(description="Y coordinate (pixels from top)")


class MoveMouseTool(_ComputerUseTool):
    """Move mouse cursor to specified coordinates."""

    name: str = "computer_move_mouse"
    description: str = "Move the mouse cursor to specified screen coordinates."
    args_schema: type[BaseModel] = MoveMouseInput

    def _run(self, x: int, y: int) -> Dict[str, Any]:
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "pyautogui not installed"}

        start_time = self._emit_tool_start("move_mouse", {"x": x, "y": y})

        try:
            # Validate coordinates
            screen_width, screen_height = self._get_screen_size()
            x = max(0, min(x, screen_width - 1))
            y = max(0, min(y, screen_height - 1))

            # Move mouse
            pyautogui.moveTo(x, y, duration=0.2)

            result = {
                "success": True,
                "message": f"Mouse moved to ({x}, {y})",
                "position": {"x": x, "y": y},
            }

            self._emit_tool_result("move_mouse", result, start_time, success=True)
            return result

        except Exception as e:
            error_result = {"success": False, "error": str(e)}
            self._emit_tool_result("move_mouse", error_result, start_time, success=False)
            return error_result


class ClickInput(BaseModel):
    """Input for clicking."""
    x: int = Field(description="X coordinate")
    y: int = Field(description="Y coordinate")
    button: str = Field(default="left", description="Mouse button: left, right, or middle")
    clicks: int = Field(default=1, description="Number of clicks (1 for single, 2 for double)")


class ClickTool(_ComputerUseTool):
    """Click at specified coordinates."""

    name: str = "computer_click"
    description: str = "Click the mouse at specified coordinates. Supports left/right click and double-click."
    args_schema: type[BaseModel] = ClickInput

    def _run(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
    ) -> Dict[str, Any]:
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "pyautogui not installed"}

        start_time = self._emit_tool_start("click", {
            "x": x, "y": y, "button": button, "clicks": clicks
        })

        try:
            # Validate
            if button not in ["left", "right", "middle"]:
                button = "left"
            clicks = max(1, min(3, clicks))

            # Click
            pyautogui.click(x, y, clicks=clicks, button=button)

            # Take screenshot after click
            time.sleep(0.3)  # Wait for UI to update
            screenshot = self._take_screenshot("click")

            result = {
                "success": True,
                "message": f"{'Double-' if clicks == 2 else ''}{button.capitalize()} clicked at ({x}, {y})",
                "position": {"x": x, "y": y},
                **screenshot,
            }

            self._emit_tool_result("click", result, start_time, success=True)
            return result

        except Exception as e:
            error_result = {"success": False, "error": str(e)}
            self._emit_tool_result("click", error_result, start_time, success=False)
            return error_result


class TypeTextInput(BaseModel):
    """Input for typing text."""
    text: str = Field(description="Text to type")
    interval: float = Field(default=0.02, description="Interval between keystrokes in seconds")


class TypeTextTool(_ComputerUseTool):
    """Type text using the keyboard."""

    name: str = "computer_type"
    description: str = "Type text using the keyboard. Use this to enter text into focused input fields."
    args_schema: type[BaseModel] = TypeTextInput

    def _run(self, text: str, interval: float = 0.02) -> Dict[str, Any]:
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "pyautogui not installed"}

        start_time = self._emit_tool_start("type", {
            "text": text[:50] + "..." if len(text) > 50 else text
        })

        try:
            # Type text
            pyautogui.typewrite(text, interval=interval)

            # Take screenshot
            time.sleep(0.2)
            screenshot = self._take_screenshot("type")

            result = {
                "success": True,
                "message": f"Typed {len(text)} characters",
                "text_length": len(text),
                **screenshot,
            }

            self._emit_tool_result("type", result, start_time, success=True)
            return result

        except Exception as e:
            error_result = {"success": False, "error": str(e)}
            self._emit_tool_result("type", error_result, start_time, success=False)
            return error_result


class PressKeyInput(BaseModel):
    """Input for pressing keys."""
    keys: str = Field(
        description="Key or key combination to press. Examples: 'enter', 'ctrl+c', 'alt+tab', 'shift+a'"
    )


class PressKeyTool(_ComputerUseTool):
    """Press keyboard keys or key combinations."""

    name: str = "computer_press"
    description: str = """Press keyboard keys or combinations.
    Examples:
    - Single key: 'enter', 'tab', 'escape', 'space'
    - With modifier: 'ctrl+c', 'ctrl+v', 'alt+tab', 'ctrl+shift+s'
    - Arrow keys: 'up', 'down', 'left', 'right'
    - Function keys: 'f1', 'f5', 'f12'
    """
    args_schema: type[BaseModel] = PressKeyInput

    def _run(self, keys: str) -> Dict[str, Any]:
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "pyautogui not installed"}

        start_time = self._emit_tool_start("press", {"keys": keys})

        try:
            # Parse key combination
            key_parts = keys.lower().replace(" ", "").split("+")

            if len(key_parts) == 1:
                # Single key
                pyautogui.press(key_parts[0])
            else:
                # Key combination with modifiers
                pyautogui.hotkey(*key_parts)

            # Take screenshot
            time.sleep(0.2)
            screenshot = self._take_screenshot("press")

            result = {
                "success": True,
                "message": f"Pressed: {keys}",
                "keys": keys,
                **screenshot,
            }

            self._emit_tool_result("press", result, start_time, success=True)
            return result

        except Exception as e:
            error_result = {"success": False, "error": str(e)}
            self._emit_tool_result("press", error_result, start_time, success=False)
            return error_result


class ScrollInput(BaseModel):
    """Input for scrolling."""
    direction: str = Field(description="Scroll direction: 'up' or 'down'")
    amount: int = Field(default=3, description="Number of scroll clicks")


class ScrollTool(_ComputerUseTool):
    """Scroll the screen."""

    name: str = "computer_scroll"
    description: str = "Scroll the screen up or down."
    args_schema: type[BaseModel] = ScrollInput

    def _run(self, direction: str, amount: int = 3) -> Dict[str, Any]:
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "pyautogui not installed"}

        start_time = self._emit_tool_start("scroll", {
            "direction": direction, "amount": amount
        })

        try:
            # Determine scroll amount (positive = up, negative = down)
            scroll_amount = abs(amount)
            if direction.lower() == "down":
                scroll_amount = -scroll_amount

            pyautogui.scroll(scroll_amount)

            # Take screenshot
            time.sleep(0.3)
            screenshot = self._take_screenshot("scroll")

            result = {
                "success": True,
                "message": f"Scrolled {direction} by {abs(amount)}",
                "direction": direction,
                "amount": amount,
                **screenshot,
            }

            self._emit_tool_result("scroll", result, start_time, success=True)
            return result

        except Exception as e:
            error_result = {"success": False, "error": str(e)}
            self._emit_tool_result("scroll", error_result, start_time, success=False)
            return error_result


class ScreenshotInput(BaseModel):
    """Input for taking screenshot."""
    pass


class ScreenshotTool(_ComputerUseTool):
    """Take a screenshot of the current screen."""

    name: str = "computer_screenshot"
    description: str = "Take a screenshot of the current screen state."
    args_schema: type[BaseModel] = ScreenshotInput

    def _run(self) -> Dict[str, Any]:
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "pyautogui not installed"}

        start_time = self._emit_tool_start("screenshot", {})

        try:
            screenshot = self._take_screenshot("manual")
            screen_width, screen_height = self._get_screen_size()

            result = {
                "success": True,
                "message": f"Screenshot captured ({screen_width}x{screen_height})",
                "screen_size": {"width": screen_width, "height": screen_height},
                **screenshot,
            }

            self._emit_tool_result("screenshot", result, start_time, success=True)
            return result

        except Exception as e:
            error_result = {"success": False, "error": str(e)}
            self._emit_tool_result("screenshot", error_result, start_time, success=False)
            return error_result


class GetScreenInfoInput(BaseModel):
    """Input for getting screen info."""
    pass


class GetScreenInfoTool(_ComputerUseTool):
    """Get screen information."""

    name: str = "computer_screen_info"
    description: str = "Get screen dimensions and mouse position."
    args_schema: type[BaseModel] = GetScreenInfoInput

    def _run(self) -> Dict[str, Any]:
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "pyautogui not installed"}

        try:
            screen_width, screen_height = self._get_screen_size()
            mouse_x, mouse_y = pyautogui.position()

            return {
                "success": True,
                "screen": {
                    "width": screen_width,
                    "height": screen_height,
                },
                "mouse_position": {
                    "x": mouse_x,
                    "y": mouse_y,
                },
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


class DragInput(BaseModel):
    """Input for dragging."""
    start_x: int = Field(description="Starting X coordinate")
    start_y: int = Field(description="Starting Y coordinate")
    end_x: int = Field(description="Ending X coordinate")
    end_y: int = Field(description="Ending Y coordinate")
    duration: float = Field(default=0.5, description="Drag duration in seconds")


class DragTool(_ComputerUseTool):
    """Drag from one position to another."""

    name: str = "computer_drag"
    description: str = "Drag the mouse from one position to another (click and hold, then release)."
    args_schema: type[BaseModel] = DragInput

    def _run(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
    ) -> Dict[str, Any]:
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "pyautogui not installed"}

        start_time = self._emit_tool_start("drag", {
            "start": {"x": start_x, "y": start_y},
            "end": {"x": end_x, "y": end_y},
        })

        try:
            # Move to start, then drag to end
            pyautogui.moveTo(start_x, start_y)
            pyautogui.drag(
                end_x - start_x,
                end_y - start_y,
                duration=duration,
            )

            # Take screenshot
            time.sleep(0.2)
            screenshot = self._take_screenshot("drag")

            result = {
                "success": True,
                "message": f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})",
                "start": {"x": start_x, "y": start_y},
                "end": {"x": end_x, "y": end_y},
                **screenshot,
            }

            self._emit_tool_result("drag", result, start_time, success=True)
            return result

        except Exception as e:
            error_result = {"success": False, "error": str(e)}
            self._emit_tool_result("drag", error_result, start_time, success=False)
            return error_result


def build_computer_use_tools(
    thread_id: str,
    emit_events: bool = True,
    save_screenshots: bool = True,
) -> List[BaseTool]:
    """
    Build computer use tools for a thread.

    Args:
        thread_id: Thread/conversation ID
        emit_events: Whether to emit events for visualization
        save_screenshots: Whether to save screenshots to disk

    Returns:
        List of computer automation tools

    Note:
        Requires pyautogui: pip install pyautogui
    """
    if not PYAUTOGUI_AVAILABLE:
        logger.warning(
            "[computer_use] pyautogui not installed. "
            "Install with: pip install pyautogui pillow"
        )
        return []

    return [
        MoveMouseTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
        ClickTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
        TypeTextTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
        PressKeyTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
        ScrollTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
        ScreenshotTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
        GetScreenInfoTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
        DragTool(thread_id=thread_id, emit_events=emit_events, save_screenshots=save_screenshots),
    ]
