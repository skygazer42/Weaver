"""
Minimal LangGraph health-check graph for CI smoke tests.
Runs a deterministic calculation without external APIs to verify the runtime works.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class CalcState(TypedDict):
    total: int


def add_one(state: CalcState) -> CalcState:
    return {"total": state.get("total", 0) + 1}


def multiply_two(state: CalcState) -> CalcState:
    return {"total": state.get("total", 0) * 2}


def subtract_three(state: CalcState) -> CalcState:
    return {"total": state.get("total", 0) - 3}


def build_graph():
    workflow = StateGraph(CalcState)
    workflow.add_node("add_one", add_one)
    workflow.add_node("multiply_two", multiply_two)
    workflow.add_node("subtract_three", subtract_three)

    workflow.add_edge(START, "add_one")
    workflow.add_edge("add_one", "multiply_two")
    workflow.add_edge("multiply_two", "subtract_three")
    workflow.add_edge("subtract_three", END)
    return workflow.compile()


if __name__ == "__main__":
    graph = build_graph()
    result = graph.invoke({"total": 5})
    print(f"Health graph result: {result['total']} (expected 7)")
