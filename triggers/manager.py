"""
Trigger Manager - Central Management for All Triggers.

Provides unified interface for managing scheduled, webhook, and event triggers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

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
from .scheduler import TriggerScheduler, get_scheduler
from .webhook import WebhookHandler, get_webhook_handler

logger = logging.getLogger(__name__)


class TriggerManager:
    """
    Central manager for all trigger types.

    Provides:
    - Unified trigger management
    - Persistence (JSON file or database)
    - Execution history
    - Event-based triggers
    """

    def __init__(
        self,
        config: Optional[TriggerConfig] = None,
        storage_path: Optional[str] = None,
    ):
        self.config = config or TriggerConfig()
        self.storage_path = Path(storage_path) if storage_path else None

        # Trigger storage
        self.triggers: Dict[str, BaseTrigger] = {}
        self.executions: List[TriggerExecution] = []

        # Sub-managers
        self.scheduler = get_scheduler()
        self.webhook_handler = get_webhook_handler()

        # Event triggers
        self.event_triggers: Dict[str, List[EventTrigger]] = {}  # event_type -> triggers
        self.event_callbacks: Dict[str, Callable] = {}

        # Execution callback (called when any trigger fires)
        self.execution_callback: Optional[Callable] = None

        # Load from storage
        if self.storage_path and self.storage_path.exists():
            self._load_triggers()

    async def start(self):
        """Start the trigger system."""
        if not self.config.enabled:
            logger.info("[trigger_manager] Trigger system is disabled")
            return

        logger.info("[trigger_manager] Starting trigger system...")
        await self.scheduler.start()
        logger.info("[trigger_manager] Trigger system started")

    async def stop(self):
        """Stop the trigger system."""
        logger.info("[trigger_manager] Stopping trigger system...")
        await self.scheduler.stop()
        logger.info("[trigger_manager] Trigger system stopped")

    def set_execution_callback(
        self,
        callback: Callable[[BaseTrigger, Dict[str, Any]], Any],
    ):
        """
        Set the callback for trigger execution.

        This callback is called whenever a trigger fires.

        Args:
            callback: Function that receives (trigger, params) and executes the task
        """
        self.execution_callback = callback

    async def add_trigger(
        self,
        trigger: Union[ScheduledTrigger, WebhookTrigger, EventTrigger],
    ) -> str:
        """
        Add a new trigger.

        Args:
            trigger: The trigger to add

        Returns:
            Trigger ID
        """
        self.triggers[trigger.id] = trigger

        if isinstance(trigger, ScheduledTrigger):
            await self.scheduler.add_trigger(
                trigger,
                callback=lambda t: self._on_trigger_fired(t),
            )
        elif isinstance(trigger, WebhookTrigger):
            self.webhook_handler.add_trigger(
                trigger,
                callback=lambda t, p: self._on_trigger_fired(t, p),
            )
        elif isinstance(trigger, EventTrigger):
            self._register_event_trigger(trigger)

        # Save to storage
        self._save_triggers()

        logger.info(
            f"[trigger_manager] Added {trigger.trigger_type.value} trigger: "
            f"{trigger.name} (id={trigger.id})"
        )

        return trigger.id

    async def remove_trigger(self, trigger_id: str) -> bool:
        """Remove a trigger."""
        trigger = self.triggers.get(trigger_id)
        if not trigger:
            return False

        if isinstance(trigger, ScheduledTrigger):
            await self.scheduler.remove_trigger(trigger_id)
        elif isinstance(trigger, WebhookTrigger):
            self.webhook_handler.remove_trigger(trigger_id)
        elif isinstance(trigger, EventTrigger):
            self._unregister_event_trigger(trigger)

        del self.triggers[trigger_id]
        self._save_triggers()

        logger.info(f"[trigger_manager] Removed trigger: {trigger.name}")
        return True

    async def update_trigger(
        self,
        trigger: Union[ScheduledTrigger, WebhookTrigger, EventTrigger],
    ) -> bool:
        """Update an existing trigger."""
        if trigger.id not in self.triggers:
            return False

        old_trigger = self.triggers[trigger.id]

        # Remove old and add new
        if isinstance(old_trigger, ScheduledTrigger):
            await self.scheduler.remove_trigger(trigger.id)
        elif isinstance(old_trigger, WebhookTrigger):
            self.webhook_handler.remove_trigger(trigger.id)
        elif isinstance(old_trigger, EventTrigger):
            self._unregister_event_trigger(old_trigger)

        # Add updated trigger
        await self.add_trigger(trigger)
        return True

    async def pause_trigger(self, trigger_id: str) -> bool:
        """Pause a trigger."""
        trigger = self.triggers.get(trigger_id)
        if not trigger:
            return False

        trigger.status = TriggerStatus.PAUSED
        trigger.updated_at = datetime.now()

        if isinstance(trigger, ScheduledTrigger):
            await self.scheduler.pause_trigger(trigger_id)

        self._save_triggers()
        return True

    async def resume_trigger(self, trigger_id: str) -> bool:
        """Resume a paused trigger."""
        trigger = self.triggers.get(trigger_id)
        if not trigger:
            return False

        if trigger.status != TriggerStatus.PAUSED:
            return False

        trigger.status = TriggerStatus.ACTIVE
        trigger.updated_at = datetime.now()

        if isinstance(trigger, ScheduledTrigger):
            await self.scheduler.resume_trigger(trigger_id)

        self._save_triggers()
        return True

    def get_trigger(self, trigger_id: str) -> Optional[BaseTrigger]:
        """Get a trigger by ID."""
        return self.triggers.get(trigger_id)

    def list_triggers(
        self,
        trigger_type: Optional[TriggerType] = None,
        status: Optional[TriggerStatus] = None,
        user_id: Optional[str] = None,
    ) -> List[BaseTrigger]:
        """List triggers with optional filtering."""
        triggers = list(self.triggers.values())

        if trigger_type:
            triggers = [t for t in triggers if t.trigger_type == trigger_type]

        if status:
            triggers = [t for t in triggers if t.status == status]

        if user_id:
            triggers = [t for t in triggers if t.user_id == user_id]

        return triggers

    async def handle_webhook(
        self,
        trigger_id: str,
        method: str,
        body: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_header: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle incoming webhook request."""
        return await self.webhook_handler.handle_request(
            trigger_id=trigger_id,
            method=method,
            body=body,
            query_params=query_params,
            headers=headers,
            auth_header=auth_header,
        )

    async def emit_event(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        source: Optional[str] = None,
    ):
        """
        Emit an internal event.

        Any event triggers listening for this event type will fire.
        """
        triggers = self.event_triggers.get(event_type, [])

        for trigger in triggers:
            if trigger.status != TriggerStatus.ACTIVE:
                continue

            # Check source filter
            if trigger.event_source and trigger.event_source != source:
                continue

            # Check data filters
            if trigger.event_filters:
                if not self._match_filters(event_data, trigger.event_filters):
                    continue

            # Fire the trigger
            await self._on_trigger_fired(trigger, {
                "event_type": event_type,
                "event_data": event_data,
                "source": source,
            })

    def get_executions(
        self,
        trigger_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[TriggerExecution]:
        """Get execution history."""
        executions = self.executions

        if trigger_id:
            executions = [e for e in executions if e.trigger_id == trigger_id]

        # Sort by start time descending
        executions = sorted(executions, key=lambda e: e.started_at, reverse=True)

        return executions[:limit]

    async def _on_trigger_fired(
        self,
        trigger: BaseTrigger,
        params: Optional[Dict[str, Any]] = None,
    ):
        """Called when a trigger fires."""
        params = params or {}

        # Create execution record
        execution = TriggerExecution(
            trigger_id=trigger.id,
            trigger_name=trigger.name,
            agent_id=trigger.agent_id,
            task=trigger.task,
            task_params={**trigger.task_params, **params},
        )

        self.executions.append(execution)

        # Trim execution history
        if len(self.executions) > self.config.execution_history_limit:
            self.executions = self.executions[-self.config.execution_history_limit:]

        # Call the execution callback
        if self.execution_callback:
            try:
                logger.info(
                    f"[trigger_manager] Executing trigger: {trigger.name} "
                    f"(agent={trigger.agent_id})"
                )

                if asyncio.iscoroutinefunction(self.execution_callback):
                    result = await self.execution_callback(trigger, execution.task_params)
                else:
                    result = self.execution_callback(trigger, execution.task_params)

                execution.mark_success(result={"status": "completed"})
                logger.info(f"[trigger_manager] Trigger '{trigger.name}' completed successfully")

            except Exception as e:
                execution.mark_failed(str(e))
                logger.error(f"[trigger_manager] Trigger '{trigger.name}' failed: {e}")

        return execution

    def _register_event_trigger(self, trigger: EventTrigger):
        """Register an event trigger."""
        if trigger.event_type not in self.event_triggers:
            self.event_triggers[trigger.event_type] = []

        self.event_triggers[trigger.event_type].append(trigger)

    def _unregister_event_trigger(self, trigger: EventTrigger):
        """Unregister an event trigger."""
        if trigger.event_type in self.event_triggers:
            self.event_triggers[trigger.event_type] = [
                t for t in self.event_triggers[trigger.event_type]
                if t.id != trigger.id
            ]

    def _match_filters(self, data: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if data matches the filters."""
        for key, expected in filters.items():
            # Support nested keys with dot notation
            value = data
            for part in key.split("."):
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    return False

            if value != expected:
                return False

        return True

    def _save_triggers(self):
        """Save triggers to storage."""
        if not self.storage_path:
            return

        try:
            data = {
                "triggers": [t.to_dict() for t in self.triggers.values()],
                "saved_at": datetime.now().isoformat(),
            }

            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"[trigger_manager] Failed to save triggers: {e}")

    def _load_triggers(self):
        """Load triggers from storage."""
        if not self.storage_path or not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for trigger_data in data.get("triggers", []):
                trigger_type = TriggerType(trigger_data.get("trigger_type", "scheduled"))

                if trigger_type == TriggerType.SCHEDULED:
                    trigger = ScheduledTrigger.from_dict(trigger_data)
                elif trigger_type == TriggerType.WEBHOOK:
                    trigger = WebhookTrigger.from_dict(trigger_data)
                elif trigger_type == TriggerType.EVENT:
                    trigger = EventTrigger.from_dict(trigger_data)
                else:
                    continue

                self.triggers[trigger.id] = trigger

            logger.info(f"[trigger_manager] Loaded {len(self.triggers)} triggers from storage")

        except Exception as e:
            logger.error(f"[trigger_manager] Failed to load triggers: {e}")


# Global trigger manager instance
_trigger_manager: Optional[TriggerManager] = None


def get_trigger_manager(
    config: Optional[TriggerConfig] = None,
    storage_path: Optional[str] = None,
) -> TriggerManager:
    """Get or create the global trigger manager."""
    global _trigger_manager

    if _trigger_manager is None:
        _trigger_manager = TriggerManager(
            config=config,
            storage_path=storage_path or "data/triggers.json",
        )

    return _trigger_manager


async def init_trigger_manager(
    config: Optional[TriggerConfig] = None,
    storage_path: Optional[str] = None,
) -> TriggerManager:
    """Initialize and start the trigger manager."""
    manager = get_trigger_manager(config, storage_path)
    await manager.start()
    return manager


async def shutdown_trigger_manager():
    """Shutdown the trigger manager."""
    global _trigger_manager
    if _trigger_manager:
        await _trigger_manager.stop()
        _trigger_manager = None
