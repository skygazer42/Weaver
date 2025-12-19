from typing import TypedDict, List, Annotated, Dict, Any, Optional
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph.message import add_messages
import operator
from common.config import settings
from .message_utils import summarize_messages
from .middleware import maybe_strip_tool_messages


def capped_add_messages(
    existing: List[BaseMessage] | None, new: List[BaseMessage] | None
) -> List[BaseMessage]:
    """
    Aggregate messages and trim to keep context bounded.

    Keeps the first N (usually system/setup) and last M recent messages.
    Controlled via settings:
    - trim_messages (bool): enable/disable
    - trim_messages_keep_first (int)
    - trim_messages_keep_last (int)
    """
    merged = add_messages(existing, new)
    merged = maybe_strip_tool_messages(merged)
    if not settings.trim_messages:
        return merged

    keep_first = max(int(getattr(settings, "trim_messages_keep_first", 1)), 0)
    keep_last = max(int(getattr(settings, "trim_messages_keep_last", 8)), 0)
    if keep_first + keep_last == 0 or len(merged) <= keep_first + keep_last:
        return merged

    head = merged[:keep_first] if keep_first else []
    tail = merged[-keep_last:] if keep_last else []
    trimmed = head + tail

    # Optional summarization of middle history
    if settings.summary_messages and len(merged) > settings.summary_messages_trigger:
        middle = merged[keep_first : len(merged) - keep_last]
        summary_msg = summarize_messages(middle)
        trimmed = head + [summary_msg] + tail

    return trimmed


class AgentState(TypedDict):
    """
    The state schema for the research agent.
    This represents the agent's "short-term memory" during a research session.
    """

    # User's original input/query
    input: str
    # Optional base64-encoded images from the user
    images: List[Dict[str, Any]]
    # Flag for clarify step
    needs_clarification: bool
    # Tool approval gating
    tool_approved: bool
    pending_tool_calls: List[Dict[str, Any]]
    # User identifier for memory/namespace
    user_id: str

    # Message history for LLM context (auto-trimmed via capped_add_messages)
    messages: Annotated[List[BaseMessage], capped_add_messages]

    # Structured research plan (list of search queries/steps)
    research_plan: List[str]

    # Current step being executed
    current_step: int

    # All scraped content from searches
    scraped_content: Annotated[List[Dict[str, Any]], operator.add]

    # Code execution results
    code_results: Annotated[List[Dict[str, Any]], operator.add]

    # Final report/answer
    final_report: str

    # Draft report for evaluator/optimizer loop
    draft_report: str

    # Evaluation feedback for optimizer
    evaluation: str

    # Evaluator verdict ("pass" / "revise")
    verdict: str

    # Routing decision
    route: str

    # Revision control
    revision_count: int
    max_revisions: int

    # Completion flag
    is_complete: bool

    # Error tracking
    errors: Annotated[List[str], operator.add]

    # Cancellation support (取消控制)
    cancel_token_id: Optional[str]   # 取消令牌 ID，用于任务取消
    is_cancelled: bool               # 是否已取消

    # Tool call accounting
    tool_call_count: int


class ResearchPlan(TypedDict):
    """Structured research plan output."""
    queries: List[str]
    reasoning: str


class SearchResult(TypedDict):
    """Search result structure."""
    query: str
    results: List[Dict[str, Any]]
    timestamp: str


class CodeExecution(TypedDict):
    """Code execution result structure."""
    code: str
    output: str
    error: str | None
    image: str | None  # Base64 encoded image if generated


class QueryState(TypedDict):
    """State for a single parallel research query."""
    query: str
