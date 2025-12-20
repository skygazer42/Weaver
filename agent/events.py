"""
Tool Execution Event System for Agent Visualization.

This module defines the event types and infrastructure for real-time
streaming of tool execution progress, similar to ChatGPT's web search
visualization.

Events:
    TOOL_START: Tool begins execution
    TOOL_PROGRESS: Execution progress update
    TOOL_SCREENSHOT: Screenshot captured
    TOOL_RESULT: Execution completed with result
    TOOL_ERROR: Execution failed with error
    TASK_UPDATE: Task list status change
    CONTENT: Text content streaming

Usage:
    from agent.events import EventEmitter, ToolEvent

    emitter = EventEmitter()

    # Register a listener
    async def my_listener(event):
        print(f"Event: {event.type}, Data: {event.data}")

    emitter.on_event(my_listener)

    # Emit events
    await emitter.emit(ToolEvent.TOOL_START, {"tool": "browser_navigate", "url": "..."})
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class ToolEventType(str, Enum):
    """Types of events that can be emitted during tool execution."""

    # Tool lifecycle events
    TOOL_START = "tool_start"  # Tool begins execution
    TOOL_PROGRESS = "tool_progress"  # Execution progress update
    TOOL_SCREENSHOT = "tool_screenshot"  # Screenshot captured
    TOOL_RESULT = "tool_result"  # Execution completed
    TOOL_ERROR = "tool_error"  # Execution failed

    # Task list events
    TASK_CREATE = "task_create"  # New task created
    TASK_UPDATE = "task_update"  # Task status changed
    TASK_COMPLETE = "task_complete"  # Task completed

    # Content events
    CONTENT = "content"  # Text content streaming
    THINKING = "thinking"  # Model thinking/reasoning

    # Session events
    AGENT_START = "agent_start"  # Agent loop started
    AGENT_ITERATION = "agent_iteration"  # Agent iteration
    AGENT_DONE = "agent_done"  # Agent loop completed

    # System events
    ERROR = "error"  # General error
    DONE = "done"  # Stream completed


# Alias for convenience
ToolEvent = ToolEventType


@dataclass
class Event:
    """Represents a single event in the event stream."""

    type: ToolEventType
    data: Dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)
    thread_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for JSON serialization."""
        return {
            "type": self.type.value if isinstance(self.type, Enum) else self.type,
            "data": self.data,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "thread_id": self.thread_id,
        }

    def to_sse(self) -> str:
        """Convert event to SSE format string."""
        data = json.dumps(self.to_dict(), ensure_ascii=False)
        return f"data: {data}\n\n"


# Type alias for event listeners
EventListener = Callable[[Event], Any]


class EventEmitter:
    """
    Event emitter for tool execution visualization.

    Supports both sync and async listeners, with thread-safe operations.
    Events can be buffered for late-joining listeners.
    """

    def __init__(
        self,
        thread_id: Optional[str] = None,
        buffer_size: int = 100,
    ):
        """
        Initialize the event emitter.

        Args:
            thread_id: Optional thread/conversation ID to tag all events
            buffer_size: Maximum number of events to buffer for replay
        """
        self.thread_id = thread_id
        self.buffer_size = buffer_size
        self._listeners: List[EventListener] = []
        self._async_listeners: List[EventListener] = []
        self._event_buffer: List[Event] = []
        self._lock = asyncio.Lock()

    def on_event(self, listener: EventListener) -> None:
        """
        Register an event listener.

        Args:
            listener: Callable that receives Event objects
        """
        if asyncio.iscoroutinefunction(listener):
            self._async_listeners.append(listener)
        else:
            self._listeners.append(listener)

    def off_event(self, listener: EventListener) -> None:
        """
        Remove an event listener.

        Args:
            listener: The listener to remove
        """
        if listener in self._listeners:
            self._listeners.remove(listener)
        if listener in self._async_listeners:
            self._async_listeners.remove(listener)

    async def emit(
        self,
        event_type: Union[ToolEventType, str],
        data: Dict[str, Any],
    ) -> Event:
        """
        Emit an event to all registered listeners.

        Args:
            event_type: The type of event
            data: Event data payload

        Returns:
            The emitted Event object
        """
        event = Event(
            type=event_type if isinstance(event_type, ToolEventType) else ToolEventType(event_type),
            data=data,
            thread_id=self.thread_id,
        )

        # Buffer the event
        async with self._lock:
            self._event_buffer.append(event)
            if len(self._event_buffer) > self.buffer_size:
                self._event_buffer.pop(0)

        # Notify sync listeners
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                logger.warning(f"[events] Sync listener error: {e}")

        # Notify async listeners
        for listener in self._async_listeners:
            try:
                await listener(event)
            except Exception as e:
                logger.warning(f"[events] Async listener error: {e}")

        logger.debug(f"[events] Emitted: {event_type.value} | {data}")
        return event

    async def emit_tool_start(
        self,
        tool_name: str,
        args: Dict[str, Any],
        description: Optional[str] = None,
    ) -> Event:
        """Convenience method to emit tool start event."""
        return await self.emit(
            ToolEvent.TOOL_START,
            {
                "tool": tool_name,
                "args": args,
                "description": description or f"Executing {tool_name}",
            },
        )

    async def emit_tool_result(
        self,
        tool_name: str,
        result: Any,
        success: bool = True,
        duration_ms: Optional[float] = None,
    ) -> Event:
        """Convenience method to emit tool result event."""
        return await self.emit(
            ToolEvent.TOOL_RESULT,
            {
                "tool": tool_name,
                "result": result,
                "success": success,
                "duration_ms": duration_ms,
            },
        )

    async def emit_screenshot(
        self,
        url: str,
        filename: str,
        action: Optional[str] = None,
        page_url: Optional[str] = None,
    ) -> Event:
        """Convenience method to emit screenshot event."""
        return await self.emit(
            ToolEvent.TOOL_SCREENSHOT,
            {
                "url": url,
                "filename": filename,
                "action": action,
                "page_url": page_url,
            },
        )

    async def emit_task_update(
        self,
        task_id: str,
        status: str,
        title: Optional[str] = None,
        progress: Optional[int] = None,
    ) -> Event:
        """Convenience method to emit task update event."""
        data = {"id": task_id, "status": status}
        if title:
            data["title"] = title
        if progress is not None:
            data["progress"] = progress
        return await self.emit(ToolEvent.TASK_UPDATE, data)

    async def emit_content(self, text: str) -> Event:
        """Convenience method to emit content event."""
        return await self.emit(ToolEvent.CONTENT, {"text": text})

    async def emit_error(self, message: str, details: Optional[Dict] = None) -> Event:
        """Convenience method to emit error event."""
        data = {"message": message}
        if details:
            data["details"] = details
        return await self.emit(ToolEvent.ERROR, data)

    async def emit_done(self, message: Optional[str] = None) -> Event:
        """Convenience method to emit done event."""
        return await self.emit(ToolEvent.DONE, {"message": message or "Stream completed"})

    def get_buffered_events(self) -> List[Event]:
        """Get all buffered events for replay."""
        return list(self._event_buffer)

    def clear_buffer(self) -> None:
        """Clear the event buffer."""
        self._event_buffer.clear()


# Global event emitter registry by thread_id
_emitters: Dict[str, EventEmitter] = {}
_emitters_lock = asyncio.Lock()


async def get_emitter(thread_id: str) -> EventEmitter:
    """
    Get or create an EventEmitter for a thread.

    Args:
        thread_id: The thread/conversation ID

    Returns:
        EventEmitter instance for the thread
    """
    async with _emitters_lock:
        if thread_id not in _emitters:
            _emitters[thread_id] = EventEmitter(thread_id=thread_id)
        return _emitters[thread_id]


async def remove_emitter(thread_id: str) -> None:
    """
    Remove an EventEmitter for a thread.

    Args:
        thread_id: The thread/conversation ID
    """
    async with _emitters_lock:
        if thread_id in _emitters:
            del _emitters[thread_id]


def get_emitter_sync(thread_id: str) -> EventEmitter:
    """
    Synchronous version of get_emitter for non-async contexts.

    Args:
        thread_id: The thread/conversation ID

    Returns:
        EventEmitter instance for the thread
    """
    if thread_id not in _emitters:
        _emitters[thread_id] = EventEmitter(thread_id=thread_id)
    return _emitters[thread_id]


# SSE Event Stream Generator
async def event_stream_generator(
    thread_id: str,
    timeout: float = 300.0,
) -> Any:
    """
    Async generator that yields SSE events for a thread.

    Usage:
        async for event_sse in event_stream_generator(thread_id):
            yield event_sse

    Args:
        thread_id: The thread/conversation ID
        timeout: Maximum time to wait for events (seconds)

    Yields:
        SSE formatted event strings
    """
    emitter = await get_emitter(thread_id)
    queue: asyncio.Queue = asyncio.Queue()

    # Register listener that puts events in queue
    async def queue_listener(event: Event):
        await queue.put(event)

    emitter.on_event(queue_listener)

    try:
        # First, yield any buffered events
        for event in emitter.get_buffered_events():
            yield event.to_sse()

        # Then, yield new events as they arrive
        start_time = time.time()
        while True:
            try:
                # Wait for event with timeout
                remaining = timeout - (time.time() - start_time)
                if remaining <= 0:
                    break

                event = await asyncio.wait_for(queue.get(), timeout=min(30, remaining))
                yield event.to_sse()

                # Check if this is the done event
                if event.type == ToolEvent.DONE:
                    break

            except asyncio.TimeoutError:
                # Send keepalive
                yield ": keepalive\n\n"

    finally:
        emitter.off_event(queue_listener)
