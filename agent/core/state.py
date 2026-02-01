import operator
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph.message import add_messages

from agent.core.message_utils import summarize_messages
from common.config import settings

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


# Execution status type
ExecutionStatus = Literal["pending", "running", "paused", "completed", "failed", "cancelled"]


class AgentState(TypedDict):
    """
    The state schema for the research agent.
    This represents the agent's "short-term memory" during a research session.

    Enhanced with fields from Manus for better tracking and control.
    """

    # ============ Input/Output ============
    # User's original input/query
    input: str
    # Optional base64-encoded images from the user
    images: List[Dict[str, Any]]
    # Final report/answer
    final_report: str
    # Draft report for evaluator/optimizer loop
    draft_report: str

    # ============ User Context ============
    # User identifier for memory/namespace
    user_id: str
    # Thread/conversation identifier
    thread_id: str
    # Agent profile ID (for GPTs-like behavior)
    agent_id: str

    # ============ Execution Control ============
    # Message history for LLM context (auto-trimmed via capped_add_messages)
    messages: Annotated[List[BaseMessage], capped_add_messages]
    # Structured research plan (list of search queries/steps)
    research_plan: List[str]
    # Current step being executed
    current_step: int
    # Total steps in plan
    total_steps: int
    # Execution status
    status: ExecutionStatus
    # Completion flag
    is_complete: bool
    # Start timestamp (ISO format)
    started_at: str
    # End timestamp (ISO format)
    ended_at: str

    # ============ Routing ============
    # Routing decision: direct, agent, web, deep, clarify
    route: str
    # Routing reasoning (from smart router)
    routing_reasoning: str
    # Routing confidence (0-1)
    routing_confidence: float
    # Suggested queries from router
    suggested_queries: List[str]

    # ============ Clarification ============
    # Flag for clarify step
    needs_clarification: bool
    # Clarification question to ask user
    clarification_question: str

    # ============ Research Data ============
    # All scraped content from searches
    scraped_content: Annotated[List[Dict[str, Any]], operator.add]
    # Code execution results
    code_results: Annotated[List[Dict[str, Any]], operator.add]
    # Summary notes from deep search
    summary_notes: List[str]
    # Sources collected
    sources: List[Dict[str, str]]

    # ============ Quality Control ============
    # Evaluation feedback for optimizer
    evaluation: str
    # Evaluator verdict ("pass" / "revise" / "incomplete")
    verdict: str
    # Structured evaluation dimensions (coverage, accuracy, freshness, coherence)
    eval_dimensions: Dict[str, float]
    # Missing topics identified by evaluator
    missing_topics: List[str]
    # Revision control
    revision_count: int
    max_revisions: int

    # ============ Tool Control ============
    # Tool approval gating
    tool_approved: bool
    # Pending tool calls awaiting approval
    pending_tool_calls: List[Dict[str, Any]]
    # Tool call accounting
    tool_call_count: int
    # Maximum tool calls allowed
    tool_call_limit: int
    # Tools enabled for this session
    enabled_tools: Dict[str, bool]

    # ============ Cancellation & Error ============
    # Cancellation support
    cancel_token_id: Optional[str]  # 取消令牌 ID
    is_cancelled: bool  # 是否已取消
    # Error tracking
    errors: Annotated[List[str], operator.add]
    # Last error message
    last_error: str

    # ============ Research Tree ============
    # Tree-based research structure (serialized dict)
    research_tree: Dict[str, Any]
    # Current branch being explored
    current_branch_id: Optional[str]
    # Maximum tree depth for exploration
    max_tree_depth: int
    # Whether tree exploration is enabled
    tree_exploration_enabled: bool

    # ============ Hierarchical Agent Control ============
    # Coordinator's chosen action (plan, research, synthesize, reflect, complete)
    coordinator_action: str
    # Coordinator's reasoning for the decision
    coordinator_reasoning: str

    # ============ Compressed Knowledge ============
    # Structured compressed knowledge from research
    compressed_knowledge: Dict[str, Any]

    # ============ Domain Routing ============
    # Detected research domain (scientific, legal, financial, etc.)
    domain: str
    # Domain-specific configuration (search hints, sources, etc.)
    domain_config: Dict[str, Any]

    # ============ Metrics ============
    # Token usage tracking
    total_input_tokens: int
    total_output_tokens: int
    # LLM call count
    llm_call_count: int
    # Search count
    search_count: int
    # Time spent in each phase (seconds)
    timing: Dict[str, float]


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
