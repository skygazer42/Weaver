"""
Task List Tool for Agent Visualization.

This tool provides structured task management for AI agents, allowing:
- Creating task lists with sections
- Tracking task progress (pending/running/completed/failed)
- Real-time visualization through events
- Persistent storage

Similar to Manus's task_list_tool.py but adapted for Weaver's LangChain-based architecture.

Usage:
    from tools.automation.task_list_tool import TaskListTool, build_task_list_tools

    tools = build_task_list_tools(thread_id="thread_123")
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Storage directory for task lists
TASK_STORAGE_DIR = "data/tasks"


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Section:
    """A section containing related tasks."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    order: int = 0


@dataclass
class Task:
    """A single task item."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str = ""
    status: TaskStatus = TaskStatus.PENDING
    section_id: str = ""
    progress: int = 0  # 0-100
    result: str = ""
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class TaskListManager:
    """
    Manages task lists for a thread.

    Provides CRUD operations for sections and tasks,
    with persistence and event emission.
    """

    def __init__(self, thread_id: str, emit_events: bool = True):
        self.thread_id = thread_id
        self.emit_events = emit_events
        self.sections: List[Section] = []
        self.tasks: List[Task] = []
        self._storage_path = Path(TASK_STORAGE_DIR) / f"{thread_id}.json"
        self._ensure_storage_dir()

    def _ensure_storage_dir(self):
        """Ensure storage directory exists."""
        Path(TASK_STORAGE_DIR).mkdir(parents=True, exist_ok=True)

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit a task event for visualization."""
        if not self.emit_events:
            return

        try:
            from agent.core.events import get_emitter_sync
            emitter = get_emitter_sync(self.thread_id)
            if emitter:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(emitter.emit(event_type, data))
                finally:
                    loop.close()
        except Exception as e:
            logger.warning(f"[task_list] Failed to emit event: {e}")

    def load(self) -> bool:
        """Load task list from storage."""
        try:
            if self._storage_path.exists():
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                self.sections = [
                    Section(**s) for s in data.get("sections", [])
                ]
                self.tasks = [
                    Task(**{**t, "status": TaskStatus(t.get("status", "pending"))})
                    for t in data.get("tasks", [])
                ]
                logger.debug(f"[task_list] Loaded {len(self.sections)} sections, {len(self.tasks)} tasks")
                return True
        except Exception as e:
            logger.error(f"[task_list] Failed to load: {e}")
        return False

    def save(self) -> bool:
        """Save task list to storage."""
        try:
            data = {
                "thread_id": self.thread_id,
                "sections": [asdict(s) for s in self.sections],
                "tasks": [
                    {**asdict(t), "status": t.status.value}
                    for t in self.tasks
                ],
                "updated_at": datetime.now().isoformat(),
            }
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"[task_list] Saved to {self._storage_path}")
            return True
        except Exception as e:
            logger.error(f"[task_list] Failed to save: {e}")
            return False

    def create_section(self, title: str) -> Section:
        """Create a new section."""
        section = Section(
            title=title,
            order=len(self.sections),
        )
        self.sections.append(section)
        self.save()

        self._emit_event("task_update", {
            "action": "section_created",
            "section": asdict(section),
        })

        return section

    def create_task(
        self,
        content: str,
        section_id: Optional[str] = None,
    ) -> Task:
        """Create a new task."""
        # Use first section if not specified
        if not section_id and self.sections:
            section_id = self.sections[0].id

        task = Task(
            content=content,
            section_id=section_id or "",
        )
        self.tasks.append(task)
        self.save()

        self._emit_event("task_update", {
            "action": "task_created",
            "task": {**asdict(task), "status": task.status.value},
        })

        return task

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: Optional[int] = None,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[Task]:
        """Update task status."""
        for task in self.tasks:
            if task.id == task_id:
                task.status = status
                task.updated_at = datetime.now().isoformat()

                if progress is not None:
                    task.progress = min(100, max(0, progress))
                if result is not None:
                    task.result = result
                if error is not None:
                    task.error = error

                self.save()

                self._emit_event("task_update", {
                    "action": "task_updated",
                    "task": {**asdict(task), "status": task.status.value},
                })

                return task
        return None

    def get_next_pending_task(self) -> Optional[Task]:
        """Get the next pending task."""
        for task in self.tasks:
            if task.status == TaskStatus.PENDING:
                return task
        return None

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get all tasks grouped by section."""
        result = []
        for section in self.sections:
            section_tasks = [
                {**asdict(t), "status": t.status.value}
                for t in self.tasks
                if t.section_id == section.id
            ]
            result.append({
                "section": asdict(section),
                "tasks": section_tasks,
            })

        # Tasks without section
        orphan_tasks = [
            {**asdict(t), "status": t.status.value}
            for t in self.tasks
            if not t.section_id or not any(s.id == t.section_id for s in self.sections)
        ]
        if orphan_tasks:
            result.append({
                "section": {"id": "default", "title": "Tasks", "order": -1},
                "tasks": orphan_tasks,
            })

        return result

    def get_progress_summary(self) -> Dict[str, Any]:
        """Get task completion progress."""
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)
        running = sum(1 for t in self.tasks if t.status == TaskStatus.RUNNING)
        failed = sum(1 for t in self.tasks if t.status == TaskStatus.FAILED)
        pending = sum(1 for t in self.tasks if t.status == TaskStatus.PENDING)

        return {
            "total": total,
            "completed": completed,
            "running": running,
            "failed": failed,
            "pending": pending,
            "progress_percent": round(completed / total * 100) if total > 0 else 0,
        }

    def clear(self) -> None:
        """Clear all tasks and sections."""
        self.sections = []
        self.tasks = []
        self.save()

        self._emit_event("task_update", {
            "action": "cleared",
        })


# Global task list managers by thread_id
_managers: Dict[str, TaskListManager] = {}


def get_task_manager(thread_id: str) -> TaskListManager:
    """Get or create a TaskListManager for a thread."""
    if thread_id not in _managers:
        manager = TaskListManager(thread_id)
        manager.load()
        _managers[thread_id] = manager
    return _managers[thread_id]


# ============================================================================
# LangChain Tool Wrappers
# ============================================================================


class CreateTasksInput(BaseModel):
    """Input for creating tasks."""
    sections: List[Dict[str, Any]] = Field(
        description="List of sections with tasks. Each section has 'title' and 'tasks' (list of task content strings)."
    )


class CreateTasksTool(BaseTool):
    """Create a structured task list with sections."""

    name: str = "create_tasks"
    description: str = """Create a structured task list with sections for organizing work.

    Input format:
    {
        "sections": [
            {
                "title": "Phase 1: Research",
                "tasks": [
                    "Search for OpenAI 2025 news",
                    "Search for Google AI updates"
                ]
            },
            {
                "title": "Phase 2: Analysis",
                "tasks": [
                    "Compare findings",
                    "Write summary"
                ]
            }
        ]
    }
    """
    args_schema: type[BaseModel] = CreateTasksInput
    thread_id: str = "default"

    def _run(self, sections: List[Dict[str, Any]]) -> Dict[str, Any]:
        manager = get_task_manager(self.thread_id)

        # Clear existing tasks
        manager.clear()

        created_sections = []
        created_tasks = []

        for section_data in sections:
            # Create section
            section = manager.create_section(section_data.get("title", "Untitled"))
            created_sections.append(asdict(section))

            # Create tasks in section
            for task_content in section_data.get("tasks", []):
                if isinstance(task_content, str) and task_content.strip():
                    task = manager.create_task(task_content.strip(), section.id)
                    created_tasks.append({**asdict(task), "status": task.status.value})

        return {
            "success": True,
            "message": f"Created {len(created_sections)} sections with {len(created_tasks)} tasks",
            "sections": created_sections,
            "tasks": created_tasks,
        }


class ViewTasksInput(BaseModel):
    """Input for viewing tasks."""
    pass


class ViewTasksTool(BaseTool):
    """View all tasks and their status."""

    name: str = "view_tasks"
    description: str = "View all tasks grouped by section, with their current status."
    args_schema: type[BaseModel] = ViewTasksInput
    thread_id: str = "default"

    def _run(self) -> Dict[str, Any]:
        manager = get_task_manager(self.thread_id)
        return {
            "task_list": manager.get_all_tasks(),
            "progress": manager.get_progress_summary(),
        }


class UpdateTaskInput(BaseModel):
    """Input for updating task status."""
    task_id: str = Field(description="ID of the task to update")
    status: str = Field(description="New status: pending, running, completed, failed, cancelled")
    progress: Optional[int] = Field(default=None, description="Progress percentage (0-100)")
    result: Optional[str] = Field(default=None, description="Result or output of the task")


class UpdateTaskTool(BaseTool):
    """Update the status of a specific task."""

    name: str = "update_task"
    description: str = "Update the status of a task. Use this after completing or starting a task."
    args_schema: type[BaseModel] = UpdateTaskInput
    thread_id: str = "default"

    def _run(
        self,
        task_id: str,
        status: str,
        progress: Optional[int] = None,
        result: Optional[str] = None,
    ) -> Dict[str, Any]:
        manager = get_task_manager(self.thread_id)

        try:
            task_status = TaskStatus(status.lower())
        except ValueError:
            return {
                "success": False,
                "error": f"Invalid status: {status}. Must be one of: pending, running, completed, failed, cancelled",
            }

        task = manager.update_task_status(
            task_id=task_id,
            status=task_status,
            progress=progress,
            result=result,
        )

        if task:
            return {
                "success": True,
                "task": {**asdict(task), "status": task.status.value},
            }
        else:
            return {
                "success": False,
                "error": f"Task not found: {task_id}",
            }


class GetNextTaskInput(BaseModel):
    """Input for getting next task."""
    pass


class GetNextTaskTool(BaseTool):
    """Get the next pending task to work on."""

    name: str = "get_next_task"
    description: str = "Get the next pending task that needs to be completed."
    args_schema: type[BaseModel] = GetNextTaskInput
    thread_id: str = "default"

    def _run(self) -> Dict[str, Any]:
        manager = get_task_manager(self.thread_id)
        task = manager.get_next_pending_task()

        if task:
            # Mark as running
            manager.update_task_status(task.id, TaskStatus.RUNNING)
            return {
                "has_next": True,
                "task": {**asdict(task), "status": TaskStatus.RUNNING.value},
            }
        else:
            return {
                "has_next": False,
                "message": "All tasks completed or no tasks available",
                "progress": manager.get_progress_summary(),
            }


def build_task_list_tools(thread_id: str) -> List[BaseTool]:
    """
    Build task list tools for a thread.

    Args:
        thread_id: Thread/conversation ID

    Returns:
        List of task management tools
    """
    return [
        CreateTasksTool(thread_id=thread_id),
        ViewTasksTool(thread_id=thread_id),
        UpdateTaskTool(thread_id=thread_id),
        GetNextTaskTool(thread_id=thread_id),
    ]
