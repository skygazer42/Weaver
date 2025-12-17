from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
import logging

from .state import AgentState
from .nodes import (
    planner_node,
    researcher_node,
    writer_node,
    should_continue_research
)

logger = logging.getLogger(__name__)


def create_research_graph(checkpointer=None):
    """
    Create the research agent graph.

    The graph flow:
    1. START -> planner (creates research plan)
    2. planner -> researcher (executes searches)
    3. researcher -> [conditional]
       - If more queries: researcher (loop)
       - If done: writer
    4. writer -> END
    """

    # Initialize the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("researcher", researcher_node)
    workflow.add_node("writer", writer_node)

    # Set entry point
    workflow.set_entry_point("planner")

    # Add edges
    workflow.add_edge("planner", "researcher")

    # Conditional edge: continue researching or move to writing
    workflow.add_conditional_edges(
        "researcher",
        should_continue_research,
        {
            "continue": "researcher",  # Loop back for next query
            "write": "writer"
        }
    )

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
        from psycopg import Connection

        # Create connection
        conn = Connection.connect(database_url)

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
