from typing import TypedDict, List, Annotated, Dict, Any, Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
import operator


class AgentState(TypedDict):
    """
    The state schema for the research agent.
    This represents the agent's "short-term memory" during a research session.
    """

    # User's original input/query
    input: str

    # Message history for LLM context
    messages: Annotated[List[BaseMessage], add_messages]

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
