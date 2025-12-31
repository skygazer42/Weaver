from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from typing import List, Dict, Any, Optional
from common.config import settings
import logging
import textwrap
import json

logger = logging.getLogger(__name__)


def _trim_text(text: str, max_len: int = 4000) -> str:
    """Truncate long text to avoid token blow-ups."""
    if not text:
        return ""
    return text[:max_len]


def _summarize_content(raw_content: str) -> Optional[str]:
    """
    Summarize raw content to keep writer context small.
    Returns None on failure so callers can fallback gracefully.
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
            prompt.format_messages(content=_trim_text(raw_content, 3500))
        )
        content = getattr(response, "content", None) or ""
        return textwrap.dedent(content).strip() or None
    except Exception as e:
        logger.warning(f"Summarization failed: {e}")
        return None


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
        try:
            from tavily import TavilyClient  # type: ignore
        except Exception as e:
            logger.error(
                "Missing dependency: tavily-python. Install with `pip install tavily-python`."
            )
            return []

        if not settings.tavily_api_key:
            logger.warning("TAVILY_API_KEY not configured; returning empty results.")
            return []

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
            summary = _summarize_content(raw_content)

            results.append({
                "title": result.get("title", ""),
                "url": url,
                "summary": summary or _trim_text(result.get("content", ""), 600),
                "snippet": _trim_text(result.get("content", ""), 600),
                "raw_excerpt": _trim_text(raw_content, 1200),
                "score": result.get("score", 0),
            })

            if len(results) >= max_results:
                break

        logger.info(f"Tavily search for '{query}' returned {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"Tavily search error: {str(e)}")
        # Return empty list to let upstream fallback gracefully
        return []


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
