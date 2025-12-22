"""
Fallback search tool with multi-engine sequencing.

Current implementation uses Tavily as the primary engine (already available in
Weaver). Engines list is forward-compatible: when additional providers are
added, plug them into `_ENGINE_HANDLERS`.
"""

from typing import Any, Dict, List, Optional
from langchain.tools import tool
import logging

from common.config import settings
from tools.search.search import tavily_search

logger = logging.getLogger(__name__)


def _tavily(query: str, max_results: int) -> List[Dict[str, Any]]:
    return tavily_search(query=query, max_results=max_results)


# Map engine key -> handler
_ENGINE_HANDLERS = {
    "tavily": _tavily,
    # future: "serper": _serper, "bing": _bing, ...
}


@tool
def fallback_search(
    query: str,
    max_results: int = 5,
    engines: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Multi-engine search with fallback.

    Args:
        query: search query string
        max_results: number of results to return
        engines: ordered list of engines; defaults to config.search_engines or ["tavily"]

    Returns:
        List of search result dicts from the first successful engine.
    """
    engine_list = engines or getattr(settings, "search_engines_list", None) or ["tavily"]
    for eng in engine_list:
        handler = _ENGINE_HANDLERS.get(eng.lower())
        if not handler:
            logger.warning(f"Unknown search engine '{eng}', skipping")
            continue
        try:
            results = handler(query=query, max_results=max_results)
            if results:
                return results
        except Exception as e:
            logger.warning(f"Engine {eng} failed: {e}")
            continue
    return []
