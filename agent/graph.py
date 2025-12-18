from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
import logging
from pathlib import Path

from .state import AgentState, QueryState
from .nodes import (
    route_node,
    direct_answer_node,
    planner_node,
    web_search_plan_node,
    clarify_node,
    writer_node,
    perform_parallel_search,
    initiate_research,
    refine_plan_node,
    evaluator_node,
    revise_report_node,
    human_review_node
)

logger = logging.getLogger(__name__)


def create_research_graph(checkpointer=None, interrupt_before=None, store=None):
    """
    Create the research agent graph.

    The graph flow:
    1. START -> planner (creates research plan)
    2. planner -> [parallel] perform_parallel_search (executes searches)
    3. perform_parallel_search -> writer (aggregates results)
    4. writer -> END
    """

    # Initialize the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("router", route_node)
    workflow.add_node("direct_answer", direct_answer_node)
    workflow.add_node("clarify", clarify_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("web_plan", web_search_plan_node)
    workflow.add_node("refine_plan", refine_plan_node)
    workflow.add_node("perform_parallel_search", perform_parallel_search)
    workflow.add_node("writer", writer_node)
    workflow.add_node("evaluator", evaluator_node)
    workflow.add_node("reviser", revise_report_node)
    workflow.add_node("human_review", human_review_node)

    # Set entry point
    workflow.set_entry_point("router")

    def route_decision(state: AgentState) -> str:
        route = state.get("route", "direct")
        if route == "web":
            return "web_plan"
        if route == "direct":
            return "direct_answer"
        return "clarify"

    workflow.add_conditional_edges(
        "router",
        route_decision,
        ["direct_answer", "web_plan", "clarify"]
    )

    def after_clarify(state: AgentState) -> str:
        return "human_review" if state.get("needs_clarification") else "planner"

    workflow.add_conditional_edges(
        "clarify",
        after_clarify,
        ["planner", "human_review"]
    )

    # Planning path (agent + deep)
    workflow.add_conditional_edges(
        "planner",
        initiate_research,
        ["perform_parallel_search"]
    )
    workflow.add_conditional_edges(
        "refine_plan",
        initiate_research,
        ["perform_parallel_search"]
    )

    # Web search only path
    workflow.add_conditional_edges(
        "web_plan",
        initiate_research,
        ["perform_parallel_search"]
    )

    # Fan-in: All parallel searches feed into the writer
    workflow.add_edge("perform_parallel_search", "writer")

    def after_writer(state: AgentState) -> str:
        return "evaluator" if state.get("route") == "deep" else "human_review"

    workflow.add_conditional_edges(
        "writer",
        after_writer,
        ["evaluator", "human_review"]
    )

    def after_evaluator(state: AgentState) -> str:
        verdict = state.get("verdict", "pass")
        revision_count = int(state.get("revision_count", 0))
        max_revisions = int(state.get("max_revisions", 0))
        if verdict == "revise" and revision_count < max_revisions:
            return "refine_plan"
        return "human_review"

    workflow.add_conditional_edges(
        "evaluator",
        after_evaluator,
        ["refine_plan", "human_review"]
    )
    workflow.add_edge("refine_plan", "perform_parallel_search")
    workflow.add_edge("reviser", "evaluator")

    # Direct answer path
    workflow.add_edge("direct_answer", "human_review")

    # Final edge
    workflow.add_edge("human_review", END)

    # Compile the graph
    graph = workflow.compile(
        checkpointer=checkpointer,
        store=store,
        interrupt_before=interrupt_before or None,
    )

    logger.info("Research graph compiled successfully")

    return graph


def export_graph_mermaid(output_path: str = "graph_mermaid.md", xray: bool = True) -> Path:
    """
    Export the compiled graph to a mermaid markdown file for visualization.
    """
    graph = create_research_graph(checkpointer=None, interrupt_before=None)
    mermaid = graph.get_graph(xray=xray).draw_mermaid()
    path = Path(output_path)
    path.write_text(f"```mermaid\n{mermaid}\n```", encoding="utf-8")
    logger.info(f"Graph mermaid exported to {path}")
    return path


def create_checkpointer(database_url: str):
    """
    Create a PostgreSQL checkpointer for state persistence.

    This allows long-running agents to pause/resume and handle failures.
    """
    try:
        import psycopg

        # Create connection (psycopg3)
        conn = psycopg.connect(database_url)

        # Create checkpointer
        checkpointer = PostgresSaver(conn)

        # Setup tables
        checkpointer.setup()

        logger.info("PostgreSQL checkpointer initialized")
        return checkpointer

    except ImportError:
        logger.warning("psycopg not installed, running without persistence")
        return None
    except Exception as e:
        logger.error(f"Failed to create checkpointer: {str(e)}")
        return None
