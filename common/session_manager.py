"""
Session Manager for Weaver.

Provides high-level CRUD operations for research sessions.
Wraps the LangGraph checkpointer for persistence and recovery.
"""

import logging
from copy import deepcopy
from dataclasses import dataclass, field
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
    deepsearch_artifacts: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "checkpoint_ts": self.checkpoint_ts,
            "parent_checkpoint_id": self.parent_checkpoint_id,
            "state": self._sanitize_state(self.state),
            "deepsearch_artifacts": self.deepsearch_artifacts,
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
            elif k == "deepsearch_artifacts" and isinstance(v, dict):
                sanitized[k] = {
                    "mode": v.get("mode"),
                    "queries_count": len(v.get("queries", []) or []),
                    "has_tree": bool(v.get("research_tree")),
                    "quality_summary": v.get("quality_summary", {}),
                }
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

            deepsearch_artifacts = self._extract_deepsearch_artifacts(state)

            return SessionState(
                thread_id=thread_id,
                state=state,
                checkpoint_ts=checkpoint_ts,
                parent_checkpoint_id=parent_id,
                deepsearch_artifacts=deepsearch_artifacts,
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

    def build_resume_state(
        self,
        thread_id: str,
        additional_input: Optional[str] = None,
        update_state: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Build a restored state payload for session resumption.

        Rehydrates deepsearch artifacts into top-level fields so graph execution
        can continue from collected context instead of starting from scratch.
        """
        session_state = self.get_session_state(thread_id)
        if not session_state:
            return None

        restored = deepcopy(session_state.state)
        artifacts = session_state.deepsearch_artifacts or {}

        if isinstance(update_state, dict):
            restored.update(update_state)

        if additional_input:
            restored["resume_input"] = additional_input

        if artifacts:
            restored["deepsearch_artifacts"] = artifacts
            if artifacts.get("queries") and not restored.get("research_plan"):
                restored["research_plan"] = list(artifacts.get("queries", []))
            if artifacts.get("research_tree") and not restored.get("research_tree"):
                restored["research_tree"] = artifacts.get("research_tree")
            if artifacts.get("quality_summary") and not restored.get("quality_summary"):
                restored["quality_summary"] = artifacts.get("quality_summary")

        restored["resumed_from_checkpoint"] = True
        restored["resumed_at"] = datetime.utcnow().isoformat()
        return restored

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

    def _extract_deepsearch_artifacts(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Extract canonical deepsearch artifacts from state snapshot."""
        if not isinstance(state, dict):
            return {}

        artifacts = state.get("deepsearch_artifacts")
        if isinstance(artifacts, dict):
            return artifacts

        queries = state.get("research_plan", []) if isinstance(state.get("research_plan", []), list) else []
        research_tree = state.get("research_tree")
        quality_summary = state.get("quality_summary")
        if not isinstance(quality_summary, dict):
            quality_summary = {
                "summary_count": len(state.get("summary_notes", []) or []),
                "source_count": len(state.get("scraped_content", []) or []),
                "revision_count": int(state.get("revision_count", 0) or 0),
                "quality_overall_score": state.get("quality_overall_score"),
            }

        if not queries and not research_tree and not quality_summary:
            return {}

        return {
            "mode": state.get("deepsearch_mode")
            or state.get("route")
            or "deepsearch",
            "queries": queries,
            "research_tree": research_tree,
            "quality_summary": quality_summary,
        }


# Global session manager instance
_session_manager: Optional[SessionManager] = None


def get_session_manager(checkpointer) -> SessionManager:
    """Get or create the global session manager."""
    global _session_manager
    if _session_manager is None or _session_manager.checkpointer != checkpointer:
        _session_manager = SessionManager(checkpointer)
    return _session_manager
