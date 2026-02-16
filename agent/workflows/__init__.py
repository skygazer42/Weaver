"""
Public API surface for `agent.workflows`.

This module is intentionally **lazy** to prevent circular import chains
between workflows and tools (e.g. research fetchers that also need URL
canonicalization helpers living in workflows).
"""

from __future__ import annotations

import importlib
from typing import Any, Dict

__all__ = [
    "initialize_enhanced_tools",
    "check_cancellation",
    "handle_cancellation",
    "run_deepsearch",
    "run_deepsearch_optimized",
    "get_deep_agent_prompt",
    "build_writer_agent",
    "build_tool_agent",
    "build_agent_tools",
    "ResponseHandler",
    "ContinuationState",
    "ToolResultInjector",
    "ContinuationHandler",
    "ResultAggregator",
    "QueryDeduplicator",
    "get_search_cache",
    "SearchCache",
]

_SYMBOL_TO_MODULE: Dict[str, str] = {
    # Graph node helpers
    "initialize_enhanced_tools": "agent.workflows.nodes",
    "check_cancellation": "agent.workflows.nodes",
    "handle_cancellation": "agent.workflows.nodes",
    # Deep research helpers
    "get_deep_agent_prompt": "agent.workflows.deep_agent",
    # Agent factories/tools
    "build_tool_agent": "agent.workflows.agent_factory",
    "build_writer_agent": "agent.workflows.agent_factory",
    "build_agent_tools": "agent.workflows.agent_tools",
    # Core workflows
    "run_deepsearch": "agent.workflows.deepsearch",
    "run_deepsearch_optimized": "agent.workflows.deepsearch_optimized",
    # Response/aggregation
    "ResponseHandler": "agent.workflows.response_handler",
    "ResultAggregator": "agent.workflows.result_aggregator",
    # Continuation helpers
    "ContinuationHandler": "agent.workflows.continuation",
    "ContinuationState": "agent.workflows.continuation",
    "ToolResultInjector": "agent.workflows.continuation",
    # Search cache (workflow-local)
    "QueryDeduplicator": "agent.workflows.search_cache",
    "SearchCache": "agent.workflows.search_cache",
    "get_search_cache": "agent.workflows.search_cache",
}


def __getattr__(name: str) -> Any:  # pragma: no cover
    module_path = _SYMBOL_TO_MODULE.get(name)
    if not module_path:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(set(list(globals().keys()) + list(_SYMBOL_TO_MODULE.keys())))
