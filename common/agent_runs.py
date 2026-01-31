"""
Agent Run Tracking - In-memory tracking of agent execution runs.

Provides FuFanmanus-like agent run management with status tracking,
metrics collection, and lifecycle management.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentRunStatus(str, Enum):
    """Agent run status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"


@dataclass
class AgentRun:
    """
    Represents a single agent execution run.

    Tracks status, timing, metrics, and provides event streaming.
    """
    id: str
    thread_id: str
    status: AgentRunStatus = AgentRunStatus.PENDING

    # Configuration
    model: str = ""
    route: str = ""
    agent_id: str = "default"
    user_id: str = ""

    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Results
    error: Optional[str] = None
    final_report: str = ""

    # Metrics
    event_count: int = 0
    token_count: int = 0
    tool_calls: int = 0

    # Event queue for streaming
    _event_queue: Optional[asyncio.Queue] = field(default=None, repr=False)
    _listeners: List[Callable] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._event_queue = asyncio.Queue()
        self._listeners = []

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate run duration in seconds."""
        if not self.started_at:
            return None
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    @property
    def is_terminal(self) -> bool:
        """Check if run is in a terminal state."""
        return self.status in {
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.STOPPED,
            AgentRunStatus.CANCELLED,
        }

    def start(self) -> None:
        """Mark run as started."""
        self.status = AgentRunStatus.RUNNING
        self.started_at = datetime.now()
        logger.info(f"Agent run {self.id} started")

    def complete(self, final_report: str = "") -> None:
        """Mark run as completed."""
        self.status = AgentRunStatus.COMPLETED
        self.completed_at = datetime.now()
        self.final_report = final_report
        logger.info(f"Agent run {self.id} completed in {self.duration_seconds:.2f}s")
        self._push_event({"type": "status", "status": "completed"})

    def fail(self, error: str) -> None:
        """Mark run as failed."""
        self.status = AgentRunStatus.FAILED
        self.completed_at = datetime.now()
        self.error = error
        logger.error(f"Agent run {self.id} failed: {error}")
        self._push_event({"type": "status", "status": "failed", "error": error})

    def stop(self, reason: str = "User requested") -> None:
        """Mark run as stopped."""
        self.status = AgentRunStatus.STOPPED
        self.completed_at = datetime.now()
        self.error = reason
        logger.info(f"Agent run {self.id} stopped: {reason}")
        self._push_event({"type": "status", "status": "stopped", "reason": reason})

    def cancel(self, reason: str = "Cancelled") -> None:
        """Mark run as cancelled."""
        self.status = AgentRunStatus.CANCELLED
        self.completed_at = datetime.now()
        self.error = reason
        logger.info(f"Agent run {self.id} cancelled: {reason}")
        self._push_event({"type": "status", "status": "cancelled", "reason": reason})

    def push_event(self, event: Dict[str, Any]) -> None:
        """Push an event to the queue for streaming."""
        self.event_count += 1
        self._push_event(event)

    def _push_event(self, event: Dict[str, Any]) -> None:
        """Internal event push with timestamp."""
        event["timestamp"] = datetime.now().isoformat()
        event["run_id"] = self.id

        if self._event_queue:
            try:
                self._event_queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"Event queue full for run {self.id}")

        # Notify listeners
        for listener in self._listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(event))
                else:
                    listener(event)
            except Exception as e:
                logger.warning(f"Event listener error: {e}")

    async def get_event(self, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """Get next event from queue with timeout."""
        if not self._event_queue:
            return None
        try:
            return await asyncio.wait_for(self._event_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def add_listener(self, listener: Callable) -> None:
        """Add an event listener."""
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable) -> None:
        """Remove an event listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "status": self.status.value,
            "model": self.model,
            "route": self.route,
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "event_count": self.event_count,
            "token_count": self.token_count,
            "tool_calls": self.tool_calls,
        }


class AgentRunRegistry:
    """
    Thread-safe registry for tracking agent runs.

    Provides run creation, lookup, and cleanup with LRU eviction.
    """

    def __init__(self, max_runs: int = 1000, ttl_seconds: float = 3600):
        self.max_runs = max_runs
        self.ttl_seconds = ttl_seconds
        self._runs: OrderedDict[str, AgentRun] = OrderedDict()
        self._thread_index: Dict[str, str] = {}  # thread_id -> run_id
        self._lock = threading.RLock()

    def create(
        self,
        thread_id: str,
        model: str = "",
        route: str = "",
        agent_id: str = "default",
        user_id: str = "",
    ) -> AgentRun:
        """
        Create a new agent run.

        Returns:
            AgentRun instance ready for execution
        """
        run_id = f"run_{uuid.uuid4().hex[:12]}"

        run = AgentRun(
            id=run_id,
            thread_id=thread_id,
            model=model,
            route=route,
            agent_id=agent_id,
            user_id=user_id,
        )

        with self._lock:
            # Evict oldest if at capacity
            while len(self._runs) >= self.max_runs:
                oldest_id, _ = self._runs.popitem(last=False)
                # Clean up thread index
                for tid, rid in list(self._thread_index.items()):
                    if rid == oldest_id:
                        del self._thread_index[tid]

            self._runs[run_id] = run
            self._thread_index[thread_id] = run_id

        logger.debug(f"Created agent run {run_id} for thread {thread_id}")
        return run

    def get(self, run_id: str) -> Optional[AgentRun]:
        """Get a run by ID."""
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                # Move to end (most recently accessed)
                self._runs.move_to_end(run_id)
            return run

    def get_by_thread(self, thread_id: str) -> Optional[AgentRun]:
        """Get the current run for a thread."""
        with self._lock:
            run_id = self._thread_index.get(thread_id)
            if run_id:
                return self._runs.get(run_id)
            return None

    def get_active_by_thread(self, thread_id: str) -> Optional[AgentRun]:
        """Get the active (non-terminal) run for a thread."""
        run = self.get_by_thread(thread_id)
        if run and not run.is_terminal:
            return run
        return None

    def list_runs(
        self,
        user_id: Optional[str] = None,
        status: Optional[AgentRunStatus] = None,
        limit: int = 50,
    ) -> List[AgentRun]:
        """List runs with optional filtering."""
        with self._lock:
            runs = list(self._runs.values())

        # Filter
        if user_id:
            runs = [r for r in runs if r.user_id == user_id]
        if status:
            runs = [r for r in runs if r.status == status]

        # Sort by creation time (newest first)
        runs.sort(key=lambda r: r.created_at, reverse=True)

        return runs[:limit]

    def cleanup_expired(self) -> int:
        """Remove expired runs. Returns count of removed runs."""
        now = datetime.now()
        expired_ids = []

        with self._lock:
            for run_id, run in self._runs.items():
                if run.is_terminal:
                    age = (now - (run.completed_at or run.created_at)).total_seconds()
                    if age > self.ttl_seconds:
                        expired_ids.append(run_id)

            for run_id in expired_ids:
                del self._runs[run_id]
                # Clean up thread index
                for tid, rid in list(self._thread_index.items()):
                    if rid == run_id:
                        del self._thread_index[tid]

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired agent runs")

        return len(expired_ids)

    def stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        with self._lock:
            status_counts = {}
            for run in self._runs.values():
                status = run.status.value
                status_counts[status] = status_counts.get(status, 0) + 1

            return {
                "total_runs": len(self._runs),
                "max_runs": self.max_runs,
                "active_threads": len(self._thread_index),
                "status_counts": status_counts,
            }


# Global registry instance
_agent_run_registry: Optional[AgentRunRegistry] = None


def get_agent_run_registry() -> AgentRunRegistry:
    """Get the global agent run registry."""
    global _agent_run_registry
    if _agent_run_registry is None:
        _agent_run_registry = AgentRunRegistry()
    return _agent_run_registry


def create_agent_run(
    thread_id: str,
    model: str = "",
    route: str = "",
    agent_id: str = "default",
    user_id: str = "",
) -> AgentRun:
    """Create a new agent run in the global registry."""
    return get_agent_run_registry().create(
        thread_id=thread_id,
        model=model,
        route=route,
        agent_id=agent_id,
        user_id=user_id,
    )


def get_agent_run(run_id: str) -> Optional[AgentRun]:
    """Get an agent run by ID."""
    return get_agent_run_registry().get(run_id)


def get_agent_run_by_thread(thread_id: str) -> Optional[AgentRun]:
    """Get the current agent run for a thread."""
    return get_agent_run_registry().get_by_thread(thread_id)
