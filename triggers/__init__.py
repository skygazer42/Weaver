"""
Trigger System for Weaver Agent.

This module provides automated triggering capabilities:
- Scheduled triggers (cron-like scheduling)
- Webhook triggers (HTTP endpoint triggers)
- Event triggers (internal event-based triggers)

Similar to Manus's triggers/ module but adapted for Weaver.

Usage:
    from triggers import TriggerManager, ScheduledTrigger, WebhookTrigger

    manager = TriggerManager()

    # Add scheduled trigger
    trigger = ScheduledTrigger(
        name="daily_report",
        schedule="0 9 * * *",  # 9 AM daily
        agent_id="report_agent",
        task="Generate daily report"
    )
    manager.add_trigger(trigger)
"""

from .manager import TriggerManager, get_trigger_manager
from .models import (
    TriggerType,
    TriggerStatus,
    BaseTrigger,
    ScheduledTrigger,
    WebhookTrigger,
    EventTrigger,
    TriggerExecution,
    TriggerConfig,
)
from .scheduler import TriggerScheduler
from .webhook import WebhookHandler

__all__ = [
    "TriggerManager",
    "get_trigger_manager",
    "TriggerType",
    "TriggerStatus",
    "BaseTrigger",
    "ScheduledTrigger",
    "WebhookTrigger",
    "EventTrigger",
    "TriggerExecution",
    "TriggerConfig",
    "TriggerScheduler",
    "WebhookHandler",
]
