"""
Helper to emit progress/screenshot events from BrowserUse sessions.

Intended to be used inside BrowserUseTool actions; keeps logic isolated.
"""

from agent.core.events import get_emitter_sync, ToolEventType


def emit_progress(thread_id: str, tool: str, action: str, info: str):
    try:
        emitter = get_emitter_sync(thread_id)
        emitter.emit_sync(ToolEventType.TOOL_PROGRESS, {"tool": tool, "action": action, "info": info})
    except Exception:
        pass


def emit_screenshot(thread_id: str, tool: str, image_b64: str, url: str = ""):
    try:
        emitter = get_emitter_sync(thread_id)
        emitter.emit_sync(
            ToolEventType.TOOL_SCREENSHOT,
            {
                "tool": tool,
                "action": "screenshot",
                "url": None,
                "page_url": url or None,
                "image": image_b64,
                "mime_type": "image/png",
            },
        )
    except Exception:
        pass
