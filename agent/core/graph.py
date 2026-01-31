import logging
from pathlib import Path

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, StateGraph

from agent.workflows.nodes import (
    agent_node,
    clarify_node,
    deepsearch_node,
    direct_answer_node,
    evaluator_node,
    human_review_node,
    initiate_research,
    perform_parallel_search,
    planner_node,
    refine_plan_node,
    revise_report_node,
    route_node,
    web_search_plan_node,
    writer_node,
)

from .state import AgentState, QueryState

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
    workflow.add_node("agent", agent_node)
    workflow.add_node("clarify", clarify_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("web_plan", web_search_plan_node)
    workflow.add_node("refine_plan", refine_plan_node)
    workflow.add_node("perform_parallel_search", perform_parallel_search)
    workflow.add_node("writer", writer_node)
    workflow.add_node("evaluator", evaluator_node)
    workflow.add_node("reviser", revise_report_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("deepsearch", deepsearch_node)

    # Set entry point
    workflow.set_entry_point("router")

    def route_decision(state: AgentState) -> str:
        route = state.get("route", "direct")
        logger.info(f"[route_decision] state['route'] = '{route}'")

        if route == "deep":
            logger.info("[route_decision] → Routing to 'deepsearch' node")
            return "deepsearch"
        if route == "agent":
            logger.info("[route_decision] → Routing to 'agent' node")
            return "agent"
        if route == "web":
            logger.info("[route_decision] → Routing to 'web_plan' node")
            return "web_plan"
        if route == "direct":
            logger.info("[route_decision] → Routing to 'direct_answer' node")
            return "direct_answer"

        logger.info("[route_decision] → Routing to 'clarify' node (default)")
        return "clarify"

    workflow.add_conditional_edges(
        "router", route_decision, ["direct_answer", "agent", "web_plan", "clarify", "deepsearch"]
    )

    def after_clarify(state: AgentState) -> str:
        return "human_review" if state.get("needs_clarification") else "planner"

    workflow.add_conditional_edges("clarify", after_clarify, ["planner", "human_review"])

    # Planning path (agent + deep)
    workflow.add_conditional_edges("planner", initiate_research, ["perform_parallel_search"])
    workflow.add_conditional_edges("refine_plan", initiate_research, ["perform_parallel_search"])

    # Web search only path
    workflow.add_conditional_edges("web_plan", initiate_research, ["perform_parallel_search"])

    # Fan-in: All parallel searches feed into the writer
    workflow.add_edge("perform_parallel_search", "writer")

    def after_writer(state: AgentState) -> str:
        return "evaluator" if state.get("route") == "deep" else "human_review"

    workflow.add_conditional_edges("writer", after_writer, ["evaluator", "human_review"])

    def after_evaluator(state: AgentState) -> str:
        """
        Decide next step based on evaluator verdict and dimensions.

        Routes:
        - "pass" → human_review (report is good)
        - "revise" with low coverage/missing topics → refine_plan (need more info)
        - "revise" with acceptable coverage → reviser (rewrite report)
        - "incomplete" → refine_plan (major gaps)
        - max_revisions exceeded → human_review (stop iterating)
        """
        verdict = state.get("verdict", "pass")
        revision_count = int(state.get("revision_count", 0))
        max_revisions = int(state.get("max_revisions", 0))

        # Check if we've exceeded max revisions
        if revision_count >= max_revisions:
            logger.info(f"Max revisions ({max_revisions}) reached, proceeding to human review")
            return "human_review"

        if verdict == "pass":
            return "human_review"

        if verdict == "incomplete":
            return "refine_plan"

        # For "revise" verdict, check if we need more research or just a rewrite
        eval_dims = state.get("eval_dimensions", {})
        coverage = eval_dims.get("coverage", 0.7)
        missing_topics = state.get("missing_topics", [])

        # Low coverage or missing topics → need more research
        if coverage < 0.6 or missing_topics:
            logger.info(f"Low coverage ({coverage:.2f}) or missing topics, routing to refine_plan")
            return "refine_plan"

        # Acceptable coverage but poor writing → rewrite
        logger.info("Coverage acceptable, routing to reviser for rewrite")
        return "reviser"

    workflow.add_conditional_edges(
        "evaluator", after_evaluator, ["refine_plan", "reviser", "human_review"]
    )

    # Reviser rewrites the report and goes back to evaluator
    workflow.add_edge("reviser", "evaluator")

    # Direct answer path
    workflow.add_edge("direct_answer", "human_review")
    workflow.add_edge("agent", "human_review")

    # Final edge
    workflow.add_edge("deepsearch", "human_review")
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
    if not database_url:
        raise ValueError("database_url is required to initialize the Postgres checkpointer.")

    # Create connection (psycopg3)
    try:
        conn = psycopg.connect(database_url)
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Postgres for checkpointer: {e}") from e

    # Create checkpointer
    checkpointer = PostgresSaver(conn)

    # Setup tables
    checkpointer.setup()

    logger.info("PostgreSQL checkpointer initialized")
    return checkpointer
