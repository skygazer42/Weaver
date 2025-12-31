"""
Tool wrappers for evented execution.

EventedTool wraps any callable or LangChain BaseTool so that start/result/error
events are emitted via agent.core.events. Designed to improve front-end
visibility (start/progress/result) similar to Manus browser/tool tracing.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, Iterable, List, Optional

from langchain_core.tools import BaseTool

from agent.core.events import get_emitter_sync, ToolEventType


class EventedTool(BaseTool):
    """Wrap a tool to emit start/result/error events."""

    name: str
    description: str
    original: Any
    thread_id: str = "default"

    def __init__(self, original: Any, thread_id: str = "default", **kwargs):
        name = getattr(original, "name", None) or getattr(original, "__name__", None)
        description = getattr(original, "description", "") or getattr(
            original, "__doc__", ""
        )
        # Preserve args schema when available (helps tool selection)
        args_schema = getattr(original, "args_schema", None)
        super().__init__(
            name=name,
            description=description,
            args_schema=args_schema,
            original=original,
            thread_id=thread_id,
            **kwargs,
        )
        self.original = original
        self.thread_id = thread_id

    def _emit_sync(self, event_type: ToolEventType, data: Dict[str, Any]):
        """Best-effort async emit from sync context."""
        emitter = get_emitter_sync(self.thread_id)
        emitter.emit_sync(event_type, data)

    def _run(self, tool_input: Any = None, **kwargs) -> Any:
        start = time.time()
        self._emit_sync(
            ToolEventType.TOOL_START,
            {"tool": self.name, "args": {"tool_input": tool_input, **kwargs}},
        )
        try:
            result = self._invoke_original(tool_input, **kwargs)
            duration = (time.time() - start) * 1000
            self._emit_sync(
                ToolEventType.TOOL_RESULT,
                {"tool": self.name, "result": result, "success": True, "duration_ms": duration},
            )
            return result
        except Exception as e:
            duration = (time.time() - start) * 1000
            self._emit_sync(
                ToolEventType.TOOL_ERROR,
                {
                    "tool": self.name,
                    "error": str(e),
                    "duration_ms": duration,
                },
            )
            raise

    async def _arun(self, tool_input: Any = None, **kwargs) -> Any:
        start = time.time()
        emitter = get_emitter_sync(self.thread_id)
        await emitter.emit(
            ToolEventType.TOOL_START,
            {"tool": self.name, "args": {"tool_input": tool_input, **kwargs}},
        )
        try:
            result = await self._invoke_original_async(tool_input, **kwargs)
            duration = (time.time() - start) * 1000
            await emitter.emit(
                ToolEventType.TOOL_RESULT,
                {"tool": self.name, "result": result, "success": True, "duration_ms": duration},
            )
            return result
        except Exception as e:
            duration = (time.time() - start) * 1000
            await emitter.emit(
                ToolEventType.TOOL_ERROR,
                {"tool": self.name, "error": str(e), "duration_ms": duration},
            )
            raise

    def _invoke_original(self, tool_input: Any = None, **kwargs):
        # BaseTool instance
        if isinstance(self.original, BaseTool):
            # If tool_input missing but kwargs provided, treat kwargs as the input payload
            payload = tool_input if tool_input is not None else (kwargs if kwargs else tool_input)
            return self.original.run(payload, **kwargs) if payload is not None else self.original.run({})
        # callable
        try:
            return self.original(tool_input, **kwargs)
        except TypeError:
            # Fallback for callables that don't take tool_input
            if kwargs:
                return self.original(**kwargs)
            return self.original()

    async def _invoke_original_async(self, tool_input: Any = None, **kwargs):
        if isinstance(self.original, BaseTool):
            # If original supports arun, prefer it
            if hasattr(self.original, "arun"):
                payload = tool_input if tool_input is not None else (kwargs if kwargs else tool_input)
                return await self.original.arun(payload, **kwargs) if payload is not None else await self.original.arun({})
            payload = tool_input if tool_input is not None else (kwargs if kwargs else tool_input)
            return self.original.run(payload, **kwargs) if payload is not None else self.original.run({})
        try:
            result = self.original(tool_input, **kwargs)
        except TypeError:
            if kwargs:
                result = self.original(**kwargs)
            else:
                result = self.original()
        if asyncio.iscoroutine(result):
            return await result
        return result


def wrap_tools_with_events(
    tools: Iterable[Any], thread_id: str = "default"
) -> List[Any]:
    """Wrap a list of tools with EventedTool, skipping ones already evented."""
    wrapped: List[Any] = []
    for tool in tools:
        name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
        # Many first-party tools already emit tool_* events (and expose a switch
        # like `emit_events`). Avoid double-emitting start/result/error.
        if isinstance(tool, EventedTool) or hasattr(tool, "emit_events") or hasattr(tool, "_emit_event"):
            wrapped.append(tool)
        else:
            wrapped.append(EventedTool(tool, thread_id=thread_id))
    return wrapped
