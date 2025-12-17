from typing import TypedDict, List, Annotated, Dict, Any
import operator


class AgentState(TypedDict):
    """
    The state schema for the research agent.
    This represents the agent's "short-term memory" during a research session.
    """

    # User's original input/query
    input: str

    # Message history for LLM context
    messages: Annotated[List[Dict[str, Any]], operator.add]

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

    # Completion flag
    is_complete: bool

    # Error tracking
    errors: Annotated[List[str], operator.add]


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
