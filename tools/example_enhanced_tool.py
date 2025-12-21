"""
Example Enhanced Tool - demonstrates WeaverTool usage

This is a complete example showing how to create tools using the new
WeaverTool base class and tool_schema decorator.
"""

from tools.base import WeaverTool, ToolResult, tool_schema
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class EnhancedSearchTool(WeaverTool):
    """
    Enhanced search tool demonstrating all WeaverTool features.

    Features demonstrated:
    - Multiple methods with schemas
    - Success/fail/partial responses
    - Metadata handling
    - Error handling
    - Type annotations
    """

    def __init__(self, api_key: str, max_retries: int = 3):
        """
        Initialize the enhanced search tool.

        Args:
            api_key: API key for the search service
            max_retries: Maximum number of retries for failed requests
        """
        self.api_key = api_key
        self.max_retries = max_retries
        super().__init__()

    @tool_schema(
        name="search_web",
        description="Search the web for current information using advanced search algorithms",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20
                },
                "search_type": {
                    "type": "string",
                    "enum": ["general", "news", "academic", "images"],
                    "description": "Type of search to perform",
                    "default": "general"
                },
                "date_range": {
                    "type": "string",
                    "enum": ["day", "week", "month", "year", "all"],
                    "description": "Time range for results",
                    "default": "all"
                }
            },
            "required": ["query"]
        }
    )
    def search(
        self,
        query: str,
        max_results: int = 5,
        search_type: str = "general",
        date_range: str = "all"
    ) -> ToolResult:
        """
        Perform a web search.

        Args:
            query: Search query
            max_results: Maximum results
            search_type: Type of search
            date_range: Date range filter

        Returns:
            ToolResult with search results
        """
        try:
            # Simulate search logic
            logger.info(f"Searching for: {query} (type={search_type}, range={date_range})")

            # Mock results
            results = [
                {
                    "title": f"Result {i+1} for '{query}'",
                    "url": f"https://example.com/result/{i+1}",
                    "snippet": f"This is a snippet for result {i+1}...",
                    "relevance_score": 0.9 - (i * 0.1),
                    "date": datetime.now().isoformat()
                }
                for i in range(min(max_results, 3))
            ]

            return self.success_response(
                {
                    "query": query,
                    "results": results,
                    "count": len(results),
                    "search_type": search_type,
                    "date_range": date_range
                },
                metadata={
                    "search_type": search_type,
                    "api_version": "v2.0",
                    "timestamp": datetime.now().isoformat(),
                    "execution_time_ms": 250
                }
            )

        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            return self.fail_response(
                f"Search failed: {str(e)}",
                metadata={
                    "error_type": type(e).__name__,
                    "query": query,
                    "timestamp": datetime.now().isoformat()
                }
            )

    @tool_schema(
        name="search_images",
        description="Search for images on the web",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Image search query"
                },
                "count": {
                    "type": "integer",
                    "description": "Number of images to return",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20
                },
                "size": {
                    "type": "string",
                    "enum": ["small", "medium", "large", "any"],
                    "description": "Preferred image size",
                    "default": "medium"
                },
                "safe_search": {
                    "type": "boolean",
                    "description": "Enable safe search filter",
                    "default": True
                }
            },
            "required": ["query"]
        }
    )
    def search_images(
        self,
        query: str,
        count: int = 5,
        size: str = "medium",
        safe_search: bool = True
    ) -> ToolResult:
        """
        Search for images.

        Args:
            query: Search query
            count: Number of images
            size: Image size preference
            safe_search: Safe search filter

        Returns:
            ToolResult with image URLs
        """
        try:
            # Mock image search
            images = [
                {
                    "url": f"https://example.com/images/{query.replace(' ', '_')}_{i+1}.jpg",
                    "thumbnail": f"https://example.com/thumbs/{query.replace(' ', '_')}_{i+1}.jpg",
                    "width": 800,
                    "height": 600,
                    "size": size,
                    "source": f"Example Source {i+1}"
                }
                for i in range(min(count, 5))
            ]

            # Partial success demo (found some but not all requested)
            if len(images) < count:
                return self.partial_response(
                    {"query": query, "images": images, "count": len(images)},
                    f"Only found {len(images)} images out of {count} requested",
                    metadata={
                        "requested": count,
                        "found": len(images),
                        "safe_search": safe_search
                    }
                )

            return self.success_response(
                {"query": query, "images": images, "count": len(images)},
                metadata={
                    "size_filter": size,
                    "safe_search": safe_search,
                    "timestamp": datetime.now().isoformat()
                }
            )

        except Exception as e:
            return self.fail_response(
                f"Image search failed: {str(e)}",
                metadata={"error_type": type(e).__name__, "query": query}
            )

    @tool_schema(
        name="get_trending",
        description="Get trending topics and searches",
        parameters={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["all", "news", "tech", "entertainment", "sports"],
                    "description": "Category for trending topics",
                    "default": "all"
                },
                "region": {
                    "type": "string",
                    "description": "Geographic region (e.g., 'US', 'UK', 'global')",
                    "default": "global"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of trending topics",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50
                }
            },
            "required": []
        }
    )
    def get_trending(
        self,
        category: str = "all",
        region: str = "global",
        limit: int = 10
    ) -> ToolResult:
        """
        Get trending topics.

        Args:
            category: Topic category
            region: Geographic region
            limit: Number of topics

        Returns:
            ToolResult with trending topics
        """
        try:
            # Mock trending topics
            topics = [
                {
                    "topic": f"Trending Topic {i+1}",
                    "category": category,
                    "search_volume": 100000 - (i * 10000),
                    "trend_direction": "up" if i < limit // 2 else "stable",
                    "region": region
                }
                for i in range(min(limit, 10))
            ]

            return self.success_response(
                {
                    "category": category,
                    "region": region,
                    "topics": topics,
                    "count": len(topics),
                    "last_updated": datetime.now().isoformat()
                },
                metadata={
                    "data_source": "trending_api_v1",
                    "update_frequency": "5 minutes",
                    "timestamp": datetime.now().isoformat()
                }
            )

        except Exception as e:
            return self.fail_response(
                f"Failed to fetch trending topics: {str(e)}",
                metadata={"error_type": type(e).__name__, "category": category}
            )


class DataAnalysisTool(WeaverTool):
    """
    Data analysis tool demonstrating numerical operations.
    """

    def __init__(self):
        super().__init__()

    @tool_schema(
        name="analyze_data",
        description="Analyze numerical data and compute statistics",
        parameters={
            "type": "object",
            "properties": {
                "data": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Array of numerical values to analyze"
                },
                "operations": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["mean", "median", "std", "min", "max", "sum"]
                    },
                    "description": "Statistical operations to perform",
                    "default": ["mean", "std", "min", "max"]
                }
            },
            "required": ["data"]
        }
    )
    def analyze(
        self,
        data: List[float],
        operations: List[str] = None
    ) -> ToolResult:
        """
        Analyze numerical data.

        Args:
            data: List of numbers
            operations: Statistics to compute

        Returns:
            ToolResult with analysis results
        """
        if not data:
            return self.fail_response("Empty data array provided")

        if operations is None:
            operations = ["mean", "std", "min", "max"]

        try:
            import statistics

            results = {}

            if "mean" in operations:
                results["mean"] = statistics.mean(data)
            if "median" in operations:
                results["median"] = statistics.median(data)
            if "std" in operations and len(data) > 1:
                results["std"] = statistics.stdev(data)
            if "min" in operations:
                results["min"] = min(data)
            if "max" in operations:
                results["max"] = max(data)
            if "sum" in operations:
                results["sum"] = sum(data)

            results["count"] = len(data)

            return self.success_response(
                results,
                metadata={
                    "data_points": len(data),
                    "operations_requested": operations,
                    "timestamp": datetime.now().isoformat()
                }
            )

        except Exception as e:
            return self.fail_response(
                f"Analysis failed: {str(e)}",
                metadata={
                    "error_type": type(e).__name__,
                    "data_length": len(data)
                }
            )


# Example usage
if __name__ == "__main__":
    print("=" * 60)
    print("Enhanced Tool Examples")
    print("=" * 60)

    # Test EnhancedSearchTool
    search_tool = EnhancedSearchTool(api_key="test-key", max_retries=3)

    print(f"\n1. Registered methods: {search_tool.list_methods()}")

    # Test web search
    result1 = search_tool.search("machine learning", max_results=3, search_type="academic")
    print(f"\n2. Web Search Result:")
    print(f"   Success: {result1.success}")
    print(f"   Output preview: {result1.output[:200]}...")

    # Test image search
    result2 = search_tool.search_images("sunset", count=10, size="large")
    print(f"\n3. Image Search Result:")
    print(f"   Success: {result2.success}")
    if result2.metadata and 'warning' in result2.metadata:
        print(f"   Warning: {result2.metadata['warning']}")

    # Test trending
    result3 = search_tool.get_trending(category="tech", limit=5)
    print(f"\n4. Trending Topics:")
    print(f"   Success: {result3.success}")

    # Test DataAnalysisTool
    data_tool = DataAnalysisTool()
    result4 = data_tool.analyze([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], operations=["mean", "median", "std"])
    print(f"\n5. Data Analysis:")
    print(f"   Result: {result4.output}")

    print("\n" + "=" * 60)
    print("[OK] All examples completed successfully!")
    print("=" * 60)
