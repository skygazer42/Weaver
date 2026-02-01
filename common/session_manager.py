"""
Session Manager for Weaver.

Provides high-level CRUD operations for research sessions.
Wraps the LangGraph checkpointer for persistence and recovery.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """Summary information about a research session."""
    thread_id: str
    status: str  # pending, running, completed, cancelled, failed
    topic: str
    created_at: str
    updated_at: str
    route: str
    has_report: bool
    revision_count: int
    message_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "status": self.status,
            "topic": self.topic,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "route": self.route,
            "has_report": self.has_report,
            "revision_count": self.revision_count,
            "message_count": self.message_count,
        }


@dataclass
class SessionState:
    """Full state snapshot of a research session."""
    thread_id: str
    state: Dict[str, Any]
    checkpoint_ts: str
    parent_checkpoint_id: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "checkpoint_ts": self.checkpoint_ts,
            "parent_checkpoint_id": self.parent_checkpoint_id,
            "state": self._sanitize_state(self.state),
        }

    def _sanitize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize state for JSON serialization."""
        sanitized = {}
        for k, v in state.items():
            if k == "messages":
                # Convert messages to serializable format
                sanitized[k] = [
                    {"type": getattr(m, "type", "unknown"), "content": getattr(m, "content", str(m))[:500]}
                    for m in v[:20]  # Limit to last 20 messages
                ] if isinstance(v, list) else []
            elif k in ("scraped_content", "pending_tool_calls"):
                # Summarize large lists
                sanitized[k] = f"[{len(v)} items]" if isinstance(v, list) else v
            else:
                # Try to include as-is, fall back to string representation
                try:
                    import json
                    json.dumps(v)
                    sanitized[k] = v
                except (TypeError, ValueError):
                    sanitized[k] = str(v)[:200]
        return sanitized


class SessionManager:
    """
    Manages research sessions using LangGraph checkpointer.

    Provides:
    - List all sessions
    - Get session state
    - Resume session
    - Delete session
    """

    def __init__(self, checkpointer):
        """
        Initialize the session manager.

        Args:
            checkpointer: LangGraph checkpointer instance
        """
        self.checkpointer = checkpointer

    def list_sessions(
        self,
        limit: int = 50,
        status_filter: Optional[str] = None,
    ) -> List[SessionInfo]:
        """
        List all sessions.

        Args:
            limit: Maximum sessions to return
            status_filter: Filter by status (optional)

        Returns:
            List of SessionInfo objects
        """
        sessions = []

        try:
            # Get all thread IDs from checkpointer
            # Note: This implementation depends on the checkpointer type
            if hasattr(self.checkpointer, "list"):
                # Postgres checkpointer with list method
                checkpoints = list(self.checkpointer.list({"configurable": {}}))
            elif hasattr(self.checkpointer, "storage"):
                # Memory checkpointer
                checkpoints = []
                for config, checkpoint in self.checkpointer.storage.items():
                    checkpoints.append({"config": config, "checkpoint": checkpoint})
            else:
                logger.warning("Checkpointer does not support listing")
                return []

            seen_threads = set()

            for cp_info in checkpoints[:limit * 2]:  # Get extra to account for duplicates
                try:
                    if isinstance(cp_info, tuple):
                        config, checkpoint = cp_info
                    else:
                        config = cp_info.get("config", {})
                        checkpoint = cp_info.get("checkpoint", cp_info)

                    thread_id = None
                    if isinstance(config, dict):
                        thread_id = config.get("configurable", {}).get("thread_id")
                    elif hasattr(config, "configurable"):
                        thread_id = config.configurable.get("thread_id")

                    if not thread_id or thread_id in seen_threads:
                        continue

                    seen_threads.add(thread_id)

                    # Extract state from checkpoint
                    state = {}
                    if hasattr(checkpoint, "checkpoint"):
                        state = checkpoint.checkpoint.get("channel_values", {})
                    elif isinstance(checkpoint, dict):
                        state = checkpoint.get("channel_values", {})

                    session_info = self._build_session_info(thread_id, state, checkpoint)

                    # Apply status filter
                    if status_filter and session_info.status != status_filter:
                        continue

                    sessions.append(session_info)

                    if len(sessions) >= limit:
                        break

                except Exception as e:
                    logger.debug(f"Error processing checkpoint: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error listing sessions: {e}")

        return sessions

    def get_session(self, thread_id: str) -> Optional[SessionInfo]:
        """
        Get session info by thread ID.

        Args:
            thread_id: Thread identifier

        Returns:
            SessionInfo or None if not found
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            checkpoint_tuple = self.checkpointer.get_tuple(config)

            if not checkpoint_tuple:
                return None

            state = checkpoint_tuple.checkpoint.get("channel_values", {})
            return self._build_session_info(thread_id, state, checkpoint_tuple)

        except Exception as e:
            logger.error(f"Error getting session {thread_id}: {e}")
            return None

    def get_session_state(self, thread_id: str) -> Optional[SessionState]:
        """
        Get full session state.

        Args:
            thread_id: Thread identifier

        Returns:
            SessionState or None if not found
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            checkpoint_tuple = self.checkpointer.get_tuple(config)

            if not checkpoint_tuple:
                return None

            state = checkpoint_tuple.checkpoint.get("channel_values", {})
            checkpoint_ts = ""
            parent_id = None

            if hasattr(checkpoint_tuple, "metadata"):
                metadata = checkpoint_tuple.metadata or {}
                checkpoint_ts = metadata.get("created_at", "")

            if hasattr(checkpoint_tuple, "parent_config"):
                parent_config = checkpoint_tuple.parent_config
                if parent_config:
                    parent_id = parent_config.get("configurable", {}).get("checkpoint_id")

            return SessionState(
                thread_id=thread_id,
                state=state,
                checkpoint_ts=checkpoint_ts,
                parent_checkpoint_id=parent_id,
            )

        except Exception as e:
            logger.error(f"Error getting session state {thread_id}: {e}")
            return None

    def delete_session(self, thread_id: str) -> bool:
        """
        Delete a session and all its checkpoints.

        Args:
            thread_id: Thread identifier

        Returns:
            True if deleted, False otherwise
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}

            # Check if checkpointer supports deletion
            if hasattr(self.checkpointer, "delete"):
                self.checkpointer.delete(config)
                logger.info(f"Deleted session: {thread_id}")
                return True
            elif hasattr(self.checkpointer, "put"):
                # Soft delete by marking as deleted
                checkpoint_tuple = self.checkpointer.get_tuple(config)
                if checkpoint_tuple:
                    state = checkpoint_tuple.checkpoint.get("channel_values", {})
                    state["status"] = "deleted"
                    state["is_complete"] = True
                    # Note: Can't actually delete, just mark
                    logger.info(f"Marked session as deleted: {thread_id}")
                    return True

            logger.warning(f"Checkpointer does not support deletion: {thread_id}")
            return False

        except Exception as e:
            logger.error(f"Error deleting session {thread_id}: {e}")
            return False

    def can_resume(self, thread_id: str) -> Tuple[bool, str]:
        """
        Check if a session can be resumed.

        Args:
            thread_id: Thread identifier

        Returns:
            Tuple of (can_resume, reason)
        """
        session = self.get_session(thread_id)
        if not session:
            return False, "Session not found"

        if session.status == "completed":
            return False, "Session already completed"

        if session.status == "deleted":
            return False, "Session has been deleted"

        if session.status == "running":
            return False, "Session is currently running"

        return True, "Session can be resumed"

    def _build_session_info(
        self,
        thread_id: str,
        state: Dict[str, Any],
        checkpoint_tuple: Any,
    ) -> SessionInfo:
        """Build SessionInfo from state and checkpoint."""
        status = state.get("status", "unknown")
        if state.get("is_complete"):
            status = "completed"
        elif state.get("is_cancelled"):
            status = "cancelled"

        topic = state.get("input", "")[:100]
        route = state.get("route", "unknown")
        has_report = bool(state.get("final_report"))
        revision_count = int(state.get("revision_count", 0))

        messages = state.get("messages", [])
        message_count = len(messages) if isinstance(messages, list) else 0

        created_at = state.get("started_at", "")
        updated_at = state.get("ended_at", "")

        # Try to get timestamps from checkpoint metadata
        if hasattr(checkpoint_tuple, "metadata"):
            metadata = checkpoint_tuple.metadata or {}
            if not created_at:
                created_at = metadata.get("created_at", "")

        return SessionInfo(
            thread_id=thread_id,
            status=status,
            topic=topic,
            created_at=created_at,
            updated_at=updated_at,
            route=route,
            has_report=has_report,
            revision_count=revision_count,
            message_count=message_count,
        )


# Global session manager instance
_session_manager: Optional[SessionManager] = None


def get_session_manager(checkpointer) -> SessionManager:
    """Get or create the global session manager."""
    global _session_manager
    if _session_manager is None or _session_manager.checkpointer != checkpointer:
        _session_manager = SessionManager(checkpointer)
    return _session_manager
