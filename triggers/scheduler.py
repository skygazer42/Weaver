"""
Trigger Scheduler for Scheduled Triggers.

Handles cron-based scheduling using APScheduler or simple time-based scheduling.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set

from .models import ScheduledTrigger, TriggerStatus

logger = logging.getLogger(__name__)


def parse_cron_field(field: str, min_val: int, max_val: int) -> Set[int]:
    """
    Parse a single cron field into a set of valid values.

    Supports:
        *       - all values
        */n     - every n values
        n       - specific value
        n-m     - range
        n,m,o   - list of values
    """
    values = set()

    for part in field.split(","):
        part = part.strip()

        if part == "*":
            values.update(range(min_val, max_val + 1))
        elif part.startswith("*/"):
            step = int(part[2:])
            values.update(range(min_val, max_val + 1, step))
        elif "-" in part and "/" in part:
            # Range with step: 1-10/2
            range_part, step = part.split("/")
            start, end = map(int, range_part.split("-"))
            values.update(range(start, end + 1, int(step)))
        elif "-" in part:
            # Range: 1-5
            start, end = map(int, part.split("-"))
            values.update(range(start, end + 1))
        else:
            # Single value
            values.add(int(part))

    return values


def parse_cron(expression: str) -> Dict[str, Set[int]]:
    """
    Parse cron expression into component sets.

    Format: "minute hour day month weekday"

    Returns dict with keys: minute, hour, day, month, weekday
    """
    parts = expression.strip().split()

    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {expression}. Expected 5 parts.")

    return {
        "minute": parse_cron_field(parts[0], 0, 59),
        "hour": parse_cron_field(parts[1], 0, 23),
        "day": parse_cron_field(parts[2], 1, 31),
        "month": parse_cron_field(parts[3], 1, 12),
        "weekday": parse_cron_field(parts[4], 0, 6),  # 0 = Monday (Python standard)
    }


def get_next_run_time(expression: str, after: datetime = None) -> datetime:
    """
    Calculate the next run time for a cron expression.

    Args:
        expression: Cron expression
        after: Start searching after this time (default: now)

    Returns:
        Next datetime matching the cron expression
    """
    if after is None:
        after = datetime.now()

    parsed = parse_cron(expression)

    # Start from the next minute
    current = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

    # Search for up to 1 year
    max_iterations = 525600  # minutes in a year

    for _ in range(max_iterations):
        if (
            current.minute in parsed["minute"]
            and current.hour in parsed["hour"]
            and current.day in parsed["day"]
            and current.month in parsed["month"]
            and current.weekday() in parsed["weekday"]
        ):
            return current

        current += timedelta(minutes=1)

    raise ValueError(f"Could not find next run time for: {expression}")


class TriggerScheduler:
    """
    Scheduler for managing scheduled triggers.

    Uses asyncio for lightweight scheduling without external dependencies.
    """

    def __init__(self):
        self.triggers: Dict[str, ScheduledTrigger] = {}
        self.tasks: Dict[str, asyncio.Task] = {}
        self.callbacks: Dict[str, Callable] = {}
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the scheduler."""
        if self._running:
            return

        self._running = True
        logger.info("[scheduler] Trigger scheduler started")

        # Start all active triggers
        for trigger_id, trigger in self.triggers.items():
            if trigger.status == TriggerStatus.ACTIVE:
                await self._start_trigger_task(trigger)

    async def stop(self):
        """Stop the scheduler."""
        self._running = False

        # Cancel all tasks
        for task in self.tasks.values():
            task.cancel()

        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)

        self.tasks.clear()
        logger.info("[scheduler] Trigger scheduler stopped")

    async def add_trigger(
        self,
        trigger: ScheduledTrigger,
        callback: Callable[[ScheduledTrigger], Any],
    ) -> None:
        """
        Add a scheduled trigger.

        Args:
            trigger: The scheduled trigger to add
            callback: Function to call when trigger fires
        """
        async with self._lock:
            self.triggers[trigger.id] = trigger
            self.callbacks[trigger.id] = callback

            # Calculate next run time
            trigger.next_run_at = get_next_run_time(trigger.schedule)
            logger.info(
                f"[scheduler] Added trigger '{trigger.name}' "
                f"(id={trigger.id}), next run: {trigger.next_run_at}"
            )

            # Start task if scheduler is running and trigger is active
            if self._running and trigger.status == TriggerStatus.ACTIVE:
                await self._start_trigger_task(trigger)

                # Run immediately if configured
                if trigger.run_immediately:
                    logger.info(f"[scheduler] Running trigger '{trigger.name}' immediately")
                    await self._execute_trigger(trigger)

    async def remove_trigger(self, trigger_id: str) -> bool:
        """Remove a trigger."""
        async with self._lock:
            if trigger_id not in self.triggers:
                return False

            # Cancel the task
            if trigger_id in self.tasks:
                self.tasks[trigger_id].cancel()
                try:
                    await self.tasks[trigger_id]
                except asyncio.CancelledError:
                    pass
                del self.tasks[trigger_id]

            # Remove trigger and callback
            del self.triggers[trigger_id]
            if trigger_id in self.callbacks:
                del self.callbacks[trigger_id]

            logger.info(f"[scheduler] Removed trigger: {trigger_id}")
            return True

    async def update_trigger(self, trigger: ScheduledTrigger) -> bool:
        """Update an existing trigger."""
        async with self._lock:
            if trigger.id not in self.triggers:
                return False

            old_trigger = self.triggers[trigger.id]
            callback = self.callbacks.get(trigger.id)

            # Cancel old task
            if trigger.id in self.tasks:
                self.tasks[trigger.id].cancel()
                try:
                    await self.tasks[trigger.id]
                except asyncio.CancelledError:
                    pass
                del self.tasks[trigger.id]

            # Update trigger
            self.triggers[trigger.id] = trigger
            trigger.next_run_at = get_next_run_time(trigger.schedule)
            trigger.updated_at = datetime.now()

            # Restart if active
            if self._running and trigger.status == TriggerStatus.ACTIVE and callback:
                await self._start_trigger_task(trigger)

            logger.info(f"[scheduler] Updated trigger: {trigger.name}")
            return True

    async def pause_trigger(self, trigger_id: str) -> bool:
        """Pause a trigger."""
        async with self._lock:
            if trigger_id not in self.triggers:
                return False

            trigger = self.triggers[trigger_id]
            trigger.status = TriggerStatus.PAUSED
            trigger.updated_at = datetime.now()

            # Cancel the task
            if trigger_id in self.tasks:
                self.tasks[trigger_id].cancel()
                try:
                    await self.tasks[trigger_id]
                except asyncio.CancelledError:
                    pass
                del self.tasks[trigger_id]

            logger.info(f"[scheduler] Paused trigger: {trigger.name}")
            return True

    async def resume_trigger(self, trigger_id: str) -> bool:
        """Resume a paused trigger."""
        async with self._lock:
            if trigger_id not in self.triggers:
                return False

            trigger = self.triggers[trigger_id]
            if trigger.status != TriggerStatus.PAUSED:
                return False

            trigger.status = TriggerStatus.ACTIVE
            trigger.updated_at = datetime.now()
            trigger.next_run_at = get_next_run_time(trigger.schedule)

            # Start task
            if self._running:
                await self._start_trigger_task(trigger)

            logger.info(f"[scheduler] Resumed trigger: {trigger.name}")
            return True

    def get_trigger(self, trigger_id: str) -> Optional[ScheduledTrigger]:
        """Get a trigger by ID."""
        return self.triggers.get(trigger_id)

    def list_triggers(self) -> List[ScheduledTrigger]:
        """List all triggers."""
        return list(self.triggers.values())

    async def _start_trigger_task(self, trigger: ScheduledTrigger) -> None:
        """Start the asyncio task for a trigger."""
        if trigger.id in self.tasks:
            return

        task = asyncio.create_task(self._trigger_loop(trigger), name=f"trigger_{trigger.id}")
        self.tasks[trigger.id] = task

    async def _trigger_loop(self, trigger: ScheduledTrigger) -> None:
        """Main loop for a scheduled trigger."""
        while self._running:
            try:
                # Get fresh trigger data
                current_trigger = self.triggers.get(trigger.id)
                if not current_trigger or current_trigger.status != TriggerStatus.ACTIVE:
                    break

                # Calculate wait time
                now = datetime.now()
                next_run = current_trigger.next_run_at

                if next_run is None:
                    next_run = get_next_run_time(current_trigger.schedule)
                    current_trigger.next_run_at = next_run

                wait_seconds = (next_run - now).total_seconds()

                if wait_seconds > 0:
                    logger.debug(
                        f"[scheduler] Trigger '{current_trigger.name}' "
                        f"waiting {wait_seconds:.0f}s until {next_run}"
                    )
                    await asyncio.sleep(wait_seconds)

                # Check if still active after sleep
                current_trigger = self.triggers.get(trigger.id)
                if not current_trigger or current_trigger.status != TriggerStatus.ACTIVE:
                    break

                # Execute the trigger
                await self._execute_trigger(current_trigger)

                # Calculate next run
                current_trigger.next_run_at = get_next_run_time(
                    current_trigger.schedule, after=datetime.now()
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[scheduler] Error in trigger loop for '{trigger.name}': {e}")
                # Wait before retrying
                await asyncio.sleep(60)

    async def _execute_trigger(self, trigger: ScheduledTrigger) -> None:
        """Execute a trigger's callback."""
        callback = self.callbacks.get(trigger.id)
        if not callback:
            logger.warning(f"[scheduler] No callback for trigger: {trigger.name}")
            return

        try:
            logger.info(f"[scheduler] Executing trigger: {trigger.name}")
            trigger.last_executed_at = datetime.now()
            trigger.execution_count += 1

            # Call the callback (may be async)
            if asyncio.iscoroutinefunction(callback):
                await callback(trigger)
            else:
                callback(trigger)

        except Exception as e:
            logger.error(f"[scheduler] Trigger execution failed for '{trigger.name}': {e}")
            trigger.failure_count += 1

            # Update status if too many failures
            if trigger.failure_count >= trigger.max_retries * 3:
                trigger.status = TriggerStatus.ERROR
                logger.warning(
                    f"[scheduler] Trigger '{trigger.name}' disabled due to repeated failures"
                )


# Global scheduler instance
_scheduler: Optional[TriggerScheduler] = None


def get_scheduler() -> TriggerScheduler:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = TriggerScheduler()
    return _scheduler


async def start_scheduler():
    """Start the global scheduler."""
    scheduler = get_scheduler()
    await scheduler.start()


async def stop_scheduler():
    """Stop the global scheduler."""
    scheduler = get_scheduler()
    await scheduler.stop()
