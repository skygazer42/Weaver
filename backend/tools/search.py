from tavily import TavilyClient
from langchain_core.tools import tool
from typing import List, Dict, Any
from config import settings
import logging

logger = logging.getLogger(__name__)


@tool
def tavily_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Perform a deep search using Tavily API.

    Args:
        query: The search query
        max_results: Maximum number of results to return

    Returns:
        List of search results with content
    """
    try:
        client = TavilyClient(api_key=settings.tavily_api_key)

        # Use advanced search depth for better content extraction
        response = client.search(
            query=query,
            search_depth="advanced",  # Returns full webpage content
            max_results=max_results,
            include_answer=True,
            include_raw_content=True,
        )

        results = []
        for result in response.get("results", []):
            results.append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "content": result.get("content", ""),
                "raw_content": result.get("raw_content", "")[:2000],  # Limit size
                "score": result.get("score", 0),
            })

        logger.info(f"Tavily search for '{query}' returned {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"Tavily search error: {str(e)}")
        return [{"error": str(e)}]


def search_multiple_queries(queries: List[str], max_results_per_query: int = 5) -> List[Dict[str, Any]]:
    """
    Execute multiple search queries in parallel.

    Args:
        queries: List of search queries
        max_results_per_query: Max results per query

    Returns:
        Combined search results
    """
    all_results = []

    for query in queries:
        results = tavily_search(query, max_results=max_results_per_query)
        all_results.extend(results)

    return all_results
