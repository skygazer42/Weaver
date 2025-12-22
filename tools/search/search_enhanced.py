"""
Tavily Search Tool - Enhanced Version using WeaverTool

This module provides web search capabilities using the Tavily API.
Enhanced version uses WeaverTool base class for better error handling
and standardized results.

Features:
- Deep web search with content extraction
- Content summarization
- Multiple query support
- Backward compatible with LangChain
"""

from tools.core.base import WeaverTool, ToolResult, tool_schema
from tavily import TavilyClient
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from typing import List, Dict, Any, Optional
from common.config import settings
import logging
import textwrap
import json

logger = logging.getLogger(__name__)


class TavilySearchTool(WeaverTool):
    """
    Enhanced Tavily search tool using WeaverTool base class.

    Provides web search with content extraction and summarization.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Tavily search tool.

        Args:
            api_key: Tavily API key (defaults to settings.tavily_api_key)
        """
        self.api_key = api_key or settings.tavily_api_key
        if not self.api_key:
            logger.warning("Tavily API key not set")
        super().__init__()

    def _trim_text(self, text: str, max_len: int = 4000) -> str:
        """Truncate long text to avoid token blow-ups."""
        if not text:
            return ""
        return text[:max_len]

    def _summarize_content(self, raw_content: str) -> Optional[str]:
        """
        Summarize raw content to keep context small.

        Args:
            raw_content: Raw webpage content

        Returns:
            Summarized content or None on failure
        """
        if not raw_content:
            return None
        if not settings.openai_api_key:
            return None

        try:
            params: Dict[str, Any] = {
                "model": settings.primary_model,
                "temperature": 0.3,
                "api_key": settings.openai_api_key,
                "timeout": settings.openai_timeout or None,
            }
            if settings.use_azure:
                params.update({
                    "azure_endpoint": settings.azure_endpoint or None,
                    "azure_deployment": settings.primary_model,
                    "api_version": settings.azure_api_version or None,
                    "api_key": settings.azure_api_key or settings.openai_api_key,
                })
            elif settings.openai_base_url:
                params["base_url"] = settings.openai_base_url

            merged_extra: Dict[str, Any] = {}
            if settings.openai_extra_body:
                try:
                    merged_extra.update(json.loads(settings.openai_extra_body))
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON in openai_extra_body; ignoring.")
            if merged_extra:
                params["extra_body"] = merged_extra

            llm = ChatOpenAI(**params)
            prompt = ChatPromptTemplate.from_messages([
                (
                    "system",
                    "You are a concise analyst. Summarize the page into 3-5 bullet points. "
                    "Keep key facts, avoid filler, cite numbers if present."
                ),
                ("human", "{content}")
            ])
            response = llm.invoke(
                prompt.format_messages(content=self._trim_text(raw_content, 3500))
            )
            content = getattr(response, "content", None) or ""
            return textwrap.dedent(content).strip() or None

        except Exception as e:
            logger.warning(f"Summarization failed: {e}")
            return None

    @tool_schema(
        name="tavily_search",
        description="Perform a deep web search using Tavily API. Returns detailed results with content extraction and summarization.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to execute"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20
                },
                "search_depth": {
                    "type": "string",
                    "enum": ["basic", "advanced"],
                    "description": "Search depth: 'basic' for quick results, 'advanced' for full content extraction",
                    "default": "advanced"
                },
                "include_answer": {
                    "type": "boolean",
                    "description": "Include AI-generated answer summary",
                    "default": True
                }
            },
            "required": ["query"]
        }
    )
    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "advanced",
        include_answer: bool = True
    ) -> ToolResult:
        """
        Perform a deep search using Tavily API.

        Args:
            query: The search query
            max_results: Maximum number of results to return
            search_depth: Search depth (basic or advanced)
            include_answer: Include AI-generated answer

        Returns:
            ToolResult with search results
        """
        if not self.api_key:
            return self.fail_response(
                "Tavily API key not configured",
                metadata={"config_required": "TAVILY_API_KEY"}
            )

        try:
            client = TavilyClient(api_key=self.api_key)

            # Use advanced search depth for better content extraction
            response = client.search(
                query=query,
                search_depth=search_depth,
                max_results=max_results,
                include_answer=include_answer,
                include_raw_content=True,
            )

            results = []
            seen_urls = set()

            # Sort results by score descending if score exists
            sorted_results = sorted(
                response.get("results", []),
                key=lambda r: r.get("score", 0),
                reverse=True
            )

            for result in sorted_results:
                url = result.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                raw_content = result.get("raw_content", "") or result.get("content", "")
                summary = self._summarize_content(raw_content)

                results.append({
                    "title": result.get("title", ""),
                    "url": url,
                    "summary": summary or self._trim_text(result.get("content", ""), 600),
                    "snippet": self._trim_text(result.get("content", ""), 600),
                    "raw_excerpt": self._trim_text(raw_content, 1200),
                    "score": result.get("score", 0),
                })

                if len(results) >= max_results:
                    break

            # Build response data
            response_data = {
                "query": query,
                "results": results,
                "count": len(results),
                "search_depth": search_depth
            }

            # Add AI answer if available
            if include_answer and "answer" in response:
                response_data["ai_answer"] = response["answer"]

            logger.info(f"Tavily search for '{query}' returned {len(results)} results")

            return self.success_response(
                response_data,
                metadata={
                    "api": "tavily",
                    "search_depth": search_depth,
                    "total_results": len(results),
                    "has_ai_answer": "answer" in response
                }
            )

        except Exception as e:
            logger.error(f"Tavily search error: {str(e)}")
            return self.fail_response(
                f"Search failed: {str(e)}",
                metadata={
                    "error_type": type(e).__name__,
                    "query": query
                }
            )

    @tool_schema(
        name="search_multiple_queries",
        description="Execute multiple search queries and combine results. Useful for comprehensive research on related topics.",
        parameters={
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of search queries to execute"
                },
                "max_results_per_query": {
                    "type": "integer",
                    "description": "Maximum results per query",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10
                }
            },
            "required": ["queries"]
        }
    )
    def search_multiple(
        self,
        queries: List[str],
        max_results_per_query: int = 5
    ) -> ToolResult:
        """
        Execute multiple search queries in sequence.

        Args:
            queries: List of search queries
            max_results_per_query: Max results per query

        Returns:
            ToolResult with combined search results
        """
        if not queries:
            return self.fail_response("No queries provided")

        all_results = []
        query_details = []
        failed_queries = []

        for query in queries:
            result = self.search(query, max_results=max_results_per_query)

            if result.success:
                try:
                    data = json.loads(result.output)
                    all_results.extend(data.get("results", []))
                    query_details.append({
                        "query": query,
                        "count": data.get("count", 0),
                        "status": "success"
                    })
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse result for query: {query}")
                    failed_queries.append(query)
            else:
                failed_queries.append(query)
                query_details.append({
                    "query": query,
                    "status": "failed",
                    "error": result.error
                })

        # Remove duplicates based on URL
        seen_urls = set()
        unique_results = []
        for result in all_results:
            url = result.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)

        response_data = {
            "queries": queries,
            "query_details": query_details,
            "results": unique_results,
            "total_results": len(unique_results),
            "failed_queries": failed_queries
        }

        # Partial success if some queries failed
        if failed_queries and unique_results:
            return self.partial_response(
                response_data,
                f"{len(failed_queries)} out of {len(queries)} queries failed",
                metadata={
                    "total_queries": len(queries),
                    "successful_queries": len(queries) - len(failed_queries),
                    "failed_count": len(failed_queries)
                }
            )

        # Complete failure
        if not unique_results:
            return self.fail_response(
                "All queries failed",
                metadata={"failed_queries": failed_queries}
            )

        # Complete success
        return self.success_response(
            response_data,
            metadata={
                "total_queries": len(queries),
                "unique_results": len(unique_results),
                "deduplication": len(all_results) - len(unique_results)
            }
        )


# Backward compatibility: keep original function signature
def tavily_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Legacy function for backward compatibility.

    This wraps the new TavilySearchTool for existing code that uses
    the @tool decorated function.

    Args:
        query: The search query
        max_results: Maximum number of results to return

    Returns:
        List of search results (legacy format)
    """
    tool = TavilySearchTool()
    result = tool.search(query, max_results=max_results)

    if result.success:
        try:
            data = json.loads(result.output)
            return data.get("results", [])
        except json.JSONDecodeError:
            logger.error("Failed to parse search results")
            return []
    else:
        logger.error(f"Search failed: {result.error}")
        return []


def search_multiple_queries(queries: List[str], max_results_per_query: int = 5) -> List[Dict[str, Any]]:
    """
    Legacy function for backward compatibility.

    Args:
        queries: List of search queries
        max_results_per_query: Max results per query

    Returns:
        Combined search results (legacy format)
    """
    tool = TavilySearchTool()
    result = tool.search_multiple(queries, max_results_per_query=max_results_per_query)

    if result.success or (result.metadata and result.metadata.get("warning")):
        try:
            data = json.loads(result.output)
            return data.get("results", [])
        except json.JSONDecodeError:
            logger.error("Failed to parse search results")
            return []
    else:
        return []


# Example usage
if __name__ == "__main__":
    print("=" * 60)
    print("Tavily Search Tool - Enhanced Version Test")
    print("=" * 60)

    if not settings.tavily_api_key:
        print("\n[!] TAVILY_API_KEY not set in environment")
        print("    Using mock mode for demonstration")

    tool = TavilySearchTool()

    print(f"\nRegistered methods: {tool.list_methods()}")
    print(f"\nSchemas:")
    for name, schema in tool.get_schemas().items():
        print(f"  - {schema.get('name')}: {schema.get('description')[:60]}...")

    # Test single search
    print("\n" + "=" * 60)
    print("Test 1: Single Search")
    print("=" * 60)

    result1 = tool.search("artificial intelligence trends 2024", max_results=3)
    print(f"Success: {result1.success}")
    if result1.success:
        print(f"Output preview: {result1.output[:300]}...")
        print(f"Metadata: {result1.metadata}")

    # Test multiple queries
    print("\n" + "=" * 60)
    print("Test 2: Multiple Queries")
    print("=" * 60)

    result2 = tool.search_multiple(
        queries=["Python async", "FastAPI tutorial", "LangChain agents"],
        max_results_per_query=2
    )
    print(f"Success: {result2.success}")
    if result2.metadata and 'warning' in result2.metadata:
        print(f"Warning: {result2.metadata['warning']}")

    # Test legacy compatibility
    print("\n" + "=" * 60)
    print("Test 3: Legacy Function Compatibility")
    print("=" * 60)

    legacy_results = tavily_search("machine learning", max_results=2)
    print(f"Legacy function returned {len(legacy_results)} results")

    print("\n" + "=" * 60)
    print("[OK] All tests completed!")
    print("=" * 60)
