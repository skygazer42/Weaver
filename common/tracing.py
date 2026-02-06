"""
Tracing and Observability for Weaver.

Provides lightweight LLM call tracing, node execution timing,
and tool invocation tracking for debugging and monitoring.

Key Features:
1. Span-based tracing (node -> LLM calls -> tool calls)
2. In-memory ring buffer storage per thread
3. Optional OTLP export
4. Decorators for easy integration
"""

import functools
import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class SpanKind(str, Enum):
    """Type of span in the trace tree."""
    NODE = "node"           # LangGraph node execution
    LLM_CALL = "llm_call"   # LLM API call
    TOOL_CALL = "tool_call" # Tool invocation
    SEARCH = "search"       # Search operation
    CRAWL = "crawl"         # URL crawling
    CUSTOM = "custom"       # Custom span


class SpanStatus(str, Enum):
    """Status of a span."""
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class TraceSpan:
    """
    A single span in the trace tree.

    Spans form a tree structure: node spans contain LLM/tool spans as children.
    """
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    parent_id: Optional[str] = None
    kind: SpanKind = SpanKind.CUSTOM
    name: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.RUNNING

    # Metadata
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    error: Optional[str] = None

    # Custom attributes
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    def finish(self, status: SpanStatus = SpanStatus.SUCCESS, error: Optional[str] = None) -> None:
        """Mark span as finished."""
        self.end_time = time.time()
        self.status = status
        if error:
            self.error = error
            self.status = SpanStatus.ERROR

    def set_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Set token usage."""
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "kind": self.kind.value,
            "name": self.name,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status.value,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "error": self.error,
            "attributes": self.attributes,
        }


@dataclass
class Trace:
    """
    A complete trace for a single thread/request.

    Contains a tree of spans representing the execution flow.
    """
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])
    thread_id: str = ""
    spans: List[TraceSpan] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def add_span(self, span: TraceSpan) -> None:
        """Add a span to the trace."""
        self.spans.append(span)

    def get_root_spans(self) -> List[TraceSpan]:
        """Get all root-level spans (no parent)."""
        return [s for s in self.spans if s.parent_id is None]

    def get_children(self, parent_id: str) -> List[TraceSpan]:
        """Get child spans of a parent."""
        return [s for s in self.spans if s.parent_id == parent_id]

    def build_tree(self) -> List[Dict[str, Any]]:
        """Build a tree structure of spans."""
        def build_node(span: TraceSpan) -> Dict[str, Any]:
            node = span.to_dict()
            children = self.get_children(span.span_id)
            if children:
                node["children"] = [build_node(c) for c in children]
            return node

        return [build_node(s) for s in self.get_root_spans()]

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics for the trace."""
        total_llm_calls = sum(1 for s in self.spans if s.kind == SpanKind.LLM_CALL)
        total_tool_calls = sum(1 for s in self.spans if s.kind == SpanKind.TOOL_CALL)
        total_input_tokens = sum(s.input_tokens for s in self.spans)
        total_output_tokens = sum(s.output_tokens for s in self.spans)
        total_duration = sum(s.duration_ms for s in self.get_root_spans())

        # Group by node name
        node_stats = {}
        for span in self.spans:
            if span.kind == SpanKind.NODE:
                node_stats[span.name] = {
                    "duration_ms": round(span.duration_ms, 2),
                    "status": span.status.value,
                }

        # Group by model
        model_stats = {}
        for span in self.spans:
            if span.kind == SpanKind.LLM_CALL and span.model:
                if span.model not in model_stats:
                    model_stats[span.model] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
                model_stats[span.model]["calls"] += 1
                model_stats[span.model]["input_tokens"] += span.input_tokens
                model_stats[span.model]["output_tokens"] += span.output_tokens

        return {
            "trace_id": self.trace_id,
            "thread_id": self.thread_id,
            "total_spans": len(self.spans),
            "total_llm_calls": total_llm_calls,
            "total_tool_calls": total_tool_calls,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_duration_ms": round(total_duration, 2),
            "nodes": node_stats,
            "models": model_stats,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trace_id": self.trace_id,
            "thread_id": self.thread_id,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "spans": self.build_tree(),
            "summary": self.get_summary(),
        }


class TraceStore:
    """
    Thread-safe in-memory trace storage with ring buffer.

    Stores the last N traces per thread for debugging.
    """

    def __init__(self, max_traces_per_thread: int = 10, max_total_traces: int = 1000):
        """
        Initialize the trace store.

        Args:
            max_traces_per_thread: Maximum traces to keep per thread
            max_total_traces: Maximum total traces across all threads
        """
        self._traces: Dict[str, List[Trace]] = {}
        self._lock = Lock()
        self._max_per_thread = max_traces_per_thread
        self._max_total = max_total_traces

    def add_trace(self, thread_id: str, trace: Trace) -> None:
        """Add a trace for a thread."""
        with self._lock:
            if thread_id not in self._traces:
                self._traces[thread_id] = []

            self._traces[thread_id].append(trace)

            # Enforce per-thread limit
            if len(self._traces[thread_id]) > self._max_per_thread:
                self._traces[thread_id] = self._traces[thread_id][-self._max_per_thread:]

            # Enforce total limit (remove oldest from oldest thread)
            total = sum(len(t) for t in self._traces.values())
            while total > self._max_total:
                oldest_thread = min(
                    self._traces.keys(),
                    key=lambda k: self._traces[k][0].created_at if self._traces[k] else float('inf')
                )
                if self._traces[oldest_thread]:
                    self._traces[oldest_thread].pop(0)
                    if not self._traces[oldest_thread]:
                        del self._traces[oldest_thread]
                total = sum(len(t) for t in self._traces.values())

    def get_traces(self, thread_id: str) -> List[Trace]:
        """Get all traces for a thread."""
        with self._lock:
            return list(self._traces.get(thread_id, []))

    def get_latest_trace(self, thread_id: str) -> Optional[Trace]:
        """Get the most recent trace for a thread."""
        with self._lock:
            traces = self._traces.get(thread_id, [])
            return traces[-1] if traces else None

    def clear_thread(self, thread_id: str) -> None:
        """Clear all traces for a thread."""
        with self._lock:
            self._traces.pop(thread_id, None)

    def clear_all(self) -> None:
        """Clear all traces."""
        with self._lock:
            self._traces.clear()

    def get_all_thread_ids(self) -> List[str]:
        """Get all thread IDs with traces."""
        with self._lock:
            return list(self._traces.keys())


class TracingContext:
    """
    Context manager for tracing a request/thread.

    Manages the current trace and span stack for nested tracing.
    """

    def __init__(self, thread_id: str, store: Optional[TraceStore] = None):
        self.thread_id = thread_id
        self.store = store
        self.trace = Trace(thread_id=thread_id)
        self._span_stack: List[TraceSpan] = []

    @property
    def current_span(self) -> Optional[TraceSpan]:
        """Get the current (innermost) span."""
        return self._span_stack[-1] if self._span_stack else None

    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.CUSTOM,
        model: str = "",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> TraceSpan:
        """Start a new span, nested under the current one if any."""
        parent_id = self.current_span.span_id if self.current_span else None

        span = TraceSpan(
            parent_id=parent_id,
            kind=kind,
            name=name,
            model=model,
            attributes=attributes or {},
        )

        self.trace.add_span(span)
        self._span_stack.append(span)
        return span

    def end_span(self, status: SpanStatus = SpanStatus.SUCCESS, error: Optional[str] = None) -> None:
        """End the current span."""
        if self._span_stack:
            span = self._span_stack.pop()
            span.finish(status, error)

    @contextmanager
    def span(
        self,
        name: str,
        kind: SpanKind = SpanKind.CUSTOM,
        model: str = "",
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """Context manager for a span."""
        span = self.start_span(name, kind, model, attributes)
        try:
            yield span
        except Exception as e:
            self.end_span(SpanStatus.ERROR, str(e))
            raise
        else:
            self.end_span(SpanStatus.SUCCESS)

    def finish(self) -> Trace:
        """Finish tracing and store the trace."""
        # Close any unclosed spans
        while self._span_stack:
            self.end_span()

        if self.store:
            self.store.add_trace(self.thread_id, self.trace)

        return self.trace


# Global trace store
_global_store: Optional[TraceStore] = None
_global_store_lock = Lock()

# Thread-local current context
import threading

_thread_local = threading.local()


def get_trace_store() -> TraceStore:
    """Get or create the global trace store."""
    global _global_store
    with _global_store_lock:
        if _global_store is None:
            from common.config import settings
            buffer_size = getattr(settings, "trace_buffer_size", 1000)
            _global_store = TraceStore(max_total_traces=buffer_size)
        return _global_store


def get_current_context() -> Optional[TracingContext]:
    """Get the current tracing context for this thread."""
    return getattr(_thread_local, "context", None)


def set_current_context(ctx: Optional[TracingContext]) -> None:
    """Set the current tracing context for this thread."""
    _thread_local.context = ctx


@contextmanager
def trace_request(thread_id: str):
    """
    Context manager to trace an entire request.

    Usage:
        with trace_request(thread_id) as ctx:
            # do work
            with ctx.span("my_operation"):
                # nested operation
    """
    from common.config import settings

    if not getattr(settings, "enable_tracing", False):
        yield None
        return

    store = get_trace_store()
    ctx = TracingContext(thread_id, store)
    old_ctx = get_current_context()
    set_current_context(ctx)

    try:
        yield ctx
    finally:
        ctx.finish()
        set_current_context(old_ctx)


def trace_node(func: F) -> F:
    """
    Decorator to trace a LangGraph node function.

    Usage:
        @trace_node
        def my_node(state, config):
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        ctx = get_current_context()
        if ctx is None:
            return func(*args, **kwargs)

        with ctx.span(func.__name__, SpanKind.NODE):
            return func(*args, **kwargs)

    return wrapper  # type: ignore


def trace_llm_call(
    model: str = "",
    name: Optional[str] = None,
):
    """
    Decorator to trace an LLM call.

    Usage:
        @trace_llm_call(model="gpt-4o")
        def call_llm(prompt):
            ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            ctx = get_current_context()
            if ctx is None:
                return func(*args, **kwargs)

            span_name = name or func.__name__
            with ctx.span(span_name, SpanKind.LLM_CALL, model=model) as span:
                result = func(*args, **kwargs)

                # Try to extract token usage from result
                if hasattr(result, "usage_metadata"):
                    usage = result.usage_metadata
                    if usage:
                        span.set_tokens(
                            usage.get("input_tokens", 0),
                            usage.get("output_tokens", 0),
                        )

                return result

        return wrapper  # type: ignore
    return decorator


def trace_tool_call(func: F) -> F:
    """
    Decorator to trace a tool call.

    Usage:
        @trace_tool_call
        def my_tool(input):
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        ctx = get_current_context()
        if ctx is None:
            return func(*args, **kwargs)

        with ctx.span(func.__name__, SpanKind.TOOL_CALL):
            return func(*args, **kwargs)

    return wrapper  # type: ignore


def record_span(
    name: str,
    kind: SpanKind = SpanKind.CUSTOM,
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    duration_ms: float = 0,
    status: SpanStatus = SpanStatus.SUCCESS,
    error: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Record a span manually (for cases where decorators don't work).

    Usage:
        record_span(
            name="llm_call",
            kind=SpanKind.LLM_CALL,
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            duration_ms=500,
        )
    """
    ctx = get_current_context()
    if ctx is None:
        return

    span = ctx.start_span(name, kind, model, attributes)
    span.set_tokens(input_tokens, output_tokens)
    span.start_time = time.time() - (duration_ms / 1000)
    ctx.end_span(status, error)


def get_trace(thread_id: str) -> Optional[Dict[str, Any]]:
    """Get the latest trace for a thread as a dict."""
    store = get_trace_store()
    trace = store.get_latest_trace(thread_id)
    return trace.to_dict() if trace else None


def get_trace_summary(thread_id: str) -> Optional[Dict[str, Any]]:
    """Get the summary of the latest trace for a thread."""
    store = get_trace_store()
    trace = store.get_latest_trace(thread_id)
    return trace.get_summary() if trace else None


def get_all_traces(thread_id: str) -> List[Dict[str, Any]]:
    """Get all traces for a thread."""
    store = get_trace_store()
    traces = store.get_traces(thread_id)
    return [t.to_dict() for t in traces]
