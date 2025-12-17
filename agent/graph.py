from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
import logging

from .state import AgentState, QueryState
from .nodes import (
    planner_node,
    writer_node,
    perform_parallel_search,
    initiate_research
)

logger = logging.getLogger(__name__)


def create_research_graph(checkpointer=None):
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
    workflow.add_node("planner", planner_node)
    workflow.add_node("perform_parallel_search", perform_parallel_search)
    workflow.add_node("writer", writer_node)

    # Set entry point
    workflow.set_entry_point("planner")

    # Conditional edge: Map-Reduce pattern
    # The planner creates the plan, then initiate_research creates a Send object
    # for each query, triggering parallel execution of perform_parallel_search.
    workflow.add_conditional_edges(
        "planner",
        initiate_research,
        ["perform_parallel_search"]
    )

    # Fan-in: All parallel searches feed into the writer
    workflow.add_edge("perform_parallel_search", "writer")

    # Final edge
    workflow.add_edge("writer", END)

    # Compile the graph
    graph = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=None,  # Can add ["writer"] for human-in-the-loop
    )

    logger.info("Research graph compiled successfully")

    return graph


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
