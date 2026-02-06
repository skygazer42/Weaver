"""
Sub-Agent Context Isolation.

Provides isolated execution contexts for parallel sub-agents.
Prevents message/state pollution between concurrent research branches.

Key Features:
1. Fork parent state for child agents
2. Merge child results back to parent
3. Message isolation between branches
4. Shared read-only context
"""

import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class SubAgentContext:
    """
    Isolated context for a sub-agent execution.

    Provides a forked view of parent state that can be
    independently modified without affecting siblings.
    """
    scope_id: str
    parent_scope_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Isolated state fields (deep copied from parent)
    messages: List[Any] = field(default_factory=list)
    research_plan: List[str] = field(default_factory=list)
    summary_notes: List[str] = field(default_factory=list)

    # Accumulated results (to be merged back)
    scraped_content: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[Dict[str, str]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # Read-only context (shared reference)
    input: str = ""
    thread_id: str = ""
    route: str = ""
    domain: str = ""

    # Execution state
    is_complete: bool = False
    is_cancelled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for state storage."""
        return {
            "scope_id": self.scope_id,
            "parent_scope_id": self.parent_scope_id,
            "created_at": self.created_at,
            "messages_count": len(self.messages),
            "scraped_content_count": len(self.scraped_content),
            "summary_notes_count": len(self.summary_notes),
            "is_complete": self.is_complete,
            "is_cancelled": self.is_cancelled,
        }


class ContextManager:
    """
    Manages sub-agent contexts for parallel execution.

    Provides:
    - Context forking for child agents
    - Result merging back to parent
    - Context lifecycle management
    """

    def __init__(self):
        self.contexts: Dict[str, SubAgentContext] = {}

    def fork(
        self,
        parent_state: Dict[str, Any],
        scope_id: str,
        parent_scope_id: Optional[str] = None,
        inherit_messages: bool = False,
    ) -> SubAgentContext:
        """
        Create a forked context from parent state.

        Args:
            parent_state: Parent agent state dictionary
            scope_id: Unique identifier for this context
            parent_scope_id: Parent context scope ID (if nested)
            inherit_messages: Whether to copy parent messages

        Returns:
            New SubAgentContext with isolated state
        """
        context = SubAgentContext(
            scope_id=scope_id,
            parent_scope_id=parent_scope_id,
        )

        # Copy read-only context
        context.input = parent_state.get("input", "")
        context.thread_id = parent_state.get("thread_id", "")
        context.route = parent_state.get("route", "")
        context.domain = parent_state.get("domain", "")

        # Optionally inherit messages (usually we don't to keep branches isolated)
        if inherit_messages:
            parent_messages = parent_state.get("messages", [])
            # Deep copy to prevent cross-contamination
            context.messages = copy.deepcopy(parent_messages[-5:])  # Keep last 5 for context

        # Copy research plan if available
        context.research_plan = list(parent_state.get("research_plan", []))

        # Register context
        self.contexts[scope_id] = context

        logger.debug(f"[ContextManager] Forked context: {scope_id} from {parent_scope_id}")

        return context

    def merge(
        self,
        parent_state: Dict[str, Any],
        child_context: SubAgentContext,
        merge_messages: bool = False,
    ) -> Dict[str, Any]:
        """
        Merge child context results back to parent state.

        Args:
            parent_state: Parent state to merge into
            child_context: Child context with results
            merge_messages: Whether to merge child messages

        Returns:
            Updated parent state dict
        """
        updates = {}

        # Merge scraped content (additive)
        if child_context.scraped_content:
            existing = parent_state.get("scraped_content", [])
            updates["scraped_content"] = existing + child_context.scraped_content

        # Merge sources (additive, deduplicated)
        if child_context.sources:
            existing = parent_state.get("sources", [])
            existing_urls = {s.get("url") for s in existing if s.get("url")}
            new_sources = [s for s in child_context.sources if s.get("url") not in existing_urls]
            updates["sources"] = existing + new_sources

        # Merge summary notes (additive)
        if child_context.summary_notes:
            existing = parent_state.get("summary_notes", [])
            updates["summary_notes"] = existing + child_context.summary_notes

        # Merge errors (additive)
        if child_context.errors:
            existing = parent_state.get("errors", [])
            updates["errors"] = existing + child_context.errors

        # Optionally merge messages (usually we don't)
        if merge_messages and child_context.messages:
            # Only merge AI responses, not the full conversation
            ai_messages = [m for m in child_context.messages if getattr(m, "type", "") == "ai"]
            if ai_messages:
                existing = parent_state.get("messages", [])
                updates["messages"] = existing + ai_messages[-2:]  # Limit to last 2

        # Update sub_agent_contexts tracking
        sub_contexts = parent_state.get("sub_agent_contexts", {})
        sub_contexts[child_context.scope_id] = child_context.to_dict()
        updates["sub_agent_contexts"] = sub_contexts

        logger.debug(
            f"[ContextManager] Merged context {child_context.scope_id}: "
            f"+{len(child_context.scraped_content)} content, "
            f"+{len(child_context.summary_notes)} notes"
        )

        return updates

    def get_context(self, scope_id: str) -> Optional[SubAgentContext]:
        """Get a context by scope ID."""
        return self.contexts.get(scope_id)

    def remove_context(self, scope_id: str) -> None:
        """Remove a context after completion."""
        if scope_id in self.contexts:
            del self.contexts[scope_id]
            logger.debug(f"[ContextManager] Removed context: {scope_id}")

    def get_active_contexts(self) -> List[SubAgentContext]:
        """Get all active (non-complete) contexts."""
        return [c for c in self.contexts.values() if not c.is_complete]

    def cancel_context(self, scope_id: str) -> None:
        """Mark a context as cancelled."""
        if scope_id in self.contexts:
            self.contexts[scope_id].is_cancelled = True
            logger.debug(f"[ContextManager] Cancelled context: {scope_id}")


def fork_state(
    parent_state: Dict[str, Any],
    scope_id: str,
    clear_messages: bool = True,
) -> Dict[str, Any]:
    """
    Create a forked state dictionary for a sub-agent.

    This is a simpler alternative to ContextManager for basic use cases.

    Args:
        parent_state: Parent state dictionary
        scope_id: Unique scope identifier
        clear_messages: Whether to clear message history

    Returns:
        Forked state dictionary
    """
    # Shallow copy the state
    forked = dict(parent_state)

    # Clear or limit messages
    if clear_messages:
        forked["messages"] = []
    else:
        # Keep only system message and last few user/ai messages
        messages = parent_state.get("messages", [])
        system_msgs = [m for m in messages if getattr(m, "type", "") == "system"]
        recent_msgs = messages[-4:] if len(messages) > 4 else messages
        forked["messages"] = system_msgs + [m for m in recent_msgs if m not in system_msgs]

    # Clear accumulated results (will be merged back)
    forked["scraped_content"] = []
    forked["sources"] = []
    forked["summary_notes"] = []
    forked["errors"] = []

    # Mark the scope
    forked["current_branch_id"] = scope_id

    logger.debug(f"[fork_state] Created fork: {scope_id}")

    return forked


def merge_state(
    parent_state: Dict[str, Any],
    child_state: Dict[str, Any],
    scope_id: str,
) -> Dict[str, Any]:
    """
    Merge child state results back to parent.

    This is a simpler alternative to ContextManager for basic use cases.

    Args:
        parent_state: Parent state dictionary
        child_state: Child state with results
        scope_id: Child scope identifier

    Returns:
        Dictionary of updates to apply to parent
    """
    updates = {}

    # Merge lists additively
    for key in ["scraped_content", "sources", "summary_notes", "errors"]:
        child_items = child_state.get(key, [])
        if child_items:
            parent_items = parent_state.get(key, [])
            updates[key] = parent_items + child_items

    # Track merged contexts
    sub_contexts = parent_state.get("sub_agent_contexts", {})
    sub_contexts[scope_id] = {
        "scope_id": scope_id,
        "merged_at": datetime.now().isoformat(),
        "scraped_count": len(child_state.get("scraped_content", [])),
        "notes_count": len(child_state.get("summary_notes", [])),
    }
    updates["sub_agent_contexts"] = sub_contexts

    logger.debug(f"[merge_state] Merged fork: {scope_id}")

    return updates


# Global context manager instance
_global_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """Get or create the global context manager."""
    global _global_context_manager
    if _global_context_manager is None:
        _global_context_manager = ContextManager()
    return _global_context_manager
