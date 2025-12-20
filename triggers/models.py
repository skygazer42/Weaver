"""
Trigger Models and Data Types.

Defines the data structures for triggers including:
- Trigger types (scheduled, webhook, event)
- Trigger status
- Trigger execution records
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class TriggerType(str, Enum):
    """Types of triggers."""
    SCHEDULED = "scheduled"  # Cron-based scheduling
    WEBHOOK = "webhook"      # HTTP webhook trigger
    EVENT = "event"          # Internal event trigger


class TriggerStatus(str, Enum):
    """Status of a trigger."""
    ACTIVE = "active"        # Trigger is active and running
    PAUSED = "paused"        # Trigger is paused
    DISABLED = "disabled"    # Trigger is disabled
    ERROR = "error"          # Trigger encountered an error


@dataclass
class TriggerConfig:
    """Global trigger system configuration."""
    enabled: bool = True
    max_concurrent_executions: int = 5
    default_timeout_seconds: int = 300  # 5 minutes
    retry_attempts: int = 3
    retry_delay_seconds: int = 60
    execution_history_limit: int = 100


@dataclass
class BaseTrigger:
    """Base class for all triggers."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    trigger_type: TriggerType = TriggerType.SCHEDULED
    status: TriggerStatus = TriggerStatus.ACTIVE

    # Agent configuration
    agent_id: str = "default"      # Which agent to use
    task: str = ""                 # Task/prompt to execute
    task_params: Dict[str, Any] = field(default_factory=dict)

    # Execution settings
    timeout_seconds: int = 300
    retry_on_failure: bool = True
    max_retries: int = 3

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_executed_at: Optional[datetime] = None
    execution_count: int = 0
    failure_count: int = 0

    # User/Owner
    user_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert trigger to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trigger_type": self.trigger_type.value,
            "status": self.status.value,
            "agent_id": self.agent_id,
            "task": self.task,
            "task_params": self.task_params,
            "timeout_seconds": self.timeout_seconds,
            "retry_on_failure": self.retry_on_failure,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_executed_at": self.last_executed_at.isoformat() if self.last_executed_at else None,
            "execution_count": self.execution_count,
            "failure_count": self.failure_count,
            "user_id": self.user_id,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseTrigger":
        """Create trigger from dictionary."""
        data = data.copy()

        # Convert string enums back
        if isinstance(data.get("trigger_type"), str):
            data["trigger_type"] = TriggerType(data["trigger_type"])
        if isinstance(data.get("status"), str):
            data["status"] = TriggerStatus(data["status"])

        # Convert datetime strings
        for dt_field in ["created_at", "updated_at", "last_executed_at"]:
            if dt_field in data and isinstance(data[dt_field], str):
                data[dt_field] = datetime.fromisoformat(data[dt_field])

        return cls(**data)


@dataclass
class ScheduledTrigger(BaseTrigger):
    """
    Scheduled trigger using cron expressions.

    Schedule format: "minute hour day month weekday"
    Examples:
        "0 9 * * *"     - Every day at 9:00 AM
        "*/15 * * * *"  - Every 15 minutes
        "0 0 1 * *"     - First day of every month
        "0 8-17 * * 1-5" - Every hour from 8-17 on weekdays
    """
    trigger_type: TriggerType = field(default=TriggerType.SCHEDULED)

    # Cron schedule
    schedule: str = "0 * * * *"  # Default: every hour

    # Schedule options
    timezone: str = "Asia/Shanghai"
    run_immediately: bool = False  # Run once immediately when created
    catch_up: bool = False         # Run missed schedules on startup
    max_instances: int = 1         # Max concurrent instances

    # Next scheduled run
    next_run_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "schedule": self.schedule,
            "timezone": self.timezone,
            "run_immediately": self.run_immediately,
            "catch_up": self.catch_up,
            "max_instances": self.max_instances,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
        })
        return data


@dataclass
class WebhookTrigger(BaseTrigger):
    """
    Webhook trigger activated by HTTP requests.

    Can validate requests and extract data from:
    - Request body (JSON)
    - Query parameters
    - Headers
    """
    trigger_type: TriggerType = field(default=TriggerType.WEBHOOK)

    # Webhook configuration
    endpoint_path: str = ""         # Custom endpoint path (auto-generated if empty)
    http_methods: List[str] = field(default_factory=lambda: ["POST"])
    require_auth: bool = False      # Require authentication
    auth_token: Optional[str] = None  # Secret token for validation

    # Request processing
    extract_body: bool = True       # Include request body in task_params
    extract_query: bool = True      # Include query params
    extract_headers: List[str] = field(default_factory=list)  # Headers to extract

    # Rate limiting
    rate_limit: Optional[int] = None  # Max requests per minute
    rate_limit_window: int = 60       # Window in seconds

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "endpoint_path": self.endpoint_path or f"/webhook/{self.id}",
            "http_methods": self.http_methods,
            "require_auth": self.require_auth,
            "extract_body": self.extract_body,
            "extract_query": self.extract_query,
            "extract_headers": self.extract_headers,
            "rate_limit": self.rate_limit,
            "rate_limit_window": self.rate_limit_window,
        })
        return data


@dataclass
class EventTrigger(BaseTrigger):
    """
    Event trigger activated by internal events.

    Listens for specific event types and can filter based on event data.
    """
    trigger_type: TriggerType = field(default=TriggerType.EVENT)

    # Event configuration
    event_type: str = ""           # Event type to listen for
    event_source: Optional[str] = None  # Filter by source
    event_filters: Dict[str, Any] = field(default_factory=dict)  # JSON path filters

    # Debouncing
    debounce_seconds: int = 0      # Minimum time between triggers
    batch_events: bool = False     # Batch multiple events
    batch_window_seconds: int = 10

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "event_type": self.event_type,
            "event_source": self.event_source,
            "event_filters": self.event_filters,
            "debounce_seconds": self.debounce_seconds,
            "batch_events": self.batch_events,
            "batch_window_seconds": self.batch_window_seconds,
        })
        return data


@dataclass
class TriggerExecution:
    """Record of a trigger execution."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trigger_id: str = ""
    trigger_name: str = ""

    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None

    # Status
    status: str = "running"  # running, success, failed, timeout, cancelled
    error_message: Optional[str] = None

    # Execution details
    agent_id: str = ""
    thread_id: Optional[str] = None
    task: str = ""
    task_params: Dict[str, Any] = field(default_factory=dict)

    # Results
    result: Optional[Dict[str, Any]] = None
    output_text: Optional[str] = None

    # Retry info
    retry_attempt: int = 0
    max_retries: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "trigger_id": self.trigger_id,
            "trigger_name": self.trigger_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error_message": self.error_message,
            "agent_id": self.agent_id,
            "thread_id": self.thread_id,
            "task": self.task,
            "task_params": self.task_params,
            "result": self.result,
            "output_text": self.output_text,
            "retry_attempt": self.retry_attempt,
            "max_retries": self.max_retries,
        }

    def mark_success(self, result: Optional[Dict[str, Any]] = None, output: Optional[str] = None):
        """Mark execution as successful."""
        self.status = "success"
        self.completed_at = datetime.now()
        self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
        self.result = result
        self.output_text = output

    def mark_failed(self, error: str):
        """Mark execution as failed."""
        self.status = "failed"
        self.completed_at = datetime.now()
        self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
        self.error_message = error

    def mark_timeout(self):
        """Mark execution as timed out."""
        self.status = "timeout"
        self.completed_at = datetime.now()
        self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
        self.error_message = "Execution timed out"

    def mark_cancelled(self):
        """Mark execution as cancelled."""
        self.status = "cancelled"
        self.completed_at = datetime.now()
        self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
