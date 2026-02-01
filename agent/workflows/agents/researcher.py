"""
Research Agent (Researcher).

Executes searches, manages sources, and analyzes results.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


class ResearchAgent:
    """
    Executes research by performing searches and analyzing results.

    Responsibilities:
    - Execute search queries
    - Analyze and filter results
    - Select relevant URLs
    - Summarize findings
    """

    def __init__(
        self,
        llm: BaseChatModel,
        search_func: Callable,
        config: Dict[str, Any] = None,
    ):
        self.llm = llm
        self.search_func = search_func
        self.config = config or {}
        self.all_searched_urls: List[str] = []
        self.selected_urls: List[str] = []

    def execute_queries(
        self,
        queries: List[str],
        max_results_per_query: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Execute a batch of search queries.

        Returns:
            List of all search results
        """
        all_results = []

        for query in queries:
            start_time = time.time()
            try:
                results = self.search_func(
                    {"query": query, "max_results": max_results_per_query},
                    config=self.config,
                )
                all_results.extend(results)

                # Track URLs
                for r in results:
                    url = r.get("url")
                    if url and url not in self.all_searched_urls:
                        self.all_searched_urls.append(url)

                elapsed = time.time() - start_time
                logger.info(f"[Researcher] Query '{query[:50]}...' → {len(results)} results ({elapsed:.2f}s)")

            except Exception as e:
                logger.error(f"[Researcher] Query failed: {query[:50]}... - {e}")

        return all_results

    def analyze_and_select(
        self,
        topic: str,
        results: List[Dict[str, Any]],
        max_urls: int = 5,
        summary_context: str = "",
    ) -> List[str]:
        """
        Analyze results and select the most relevant URLs.

        Returns:
            List of selected URLs
        """
        if not results:
            return []

        # Filter already selected
        available = [r for r in results if r.get("url") and r.get("url") not in self.selected_urls]
        if not available:
            return []

        # Format for LLM analysis
        formatted = []
        for i, r in enumerate(available[:20], 1):
            formatted.append(
                f"[{i}] {r.get('title', 'N/A')}\n"
                f"URL: {r.get('url', '')}\n"
                f"Score: {r.get('score', 0)}\n"
                f"Summary: {(r.get('summary') or r.get('snippet') or '')[:300]}"
            )

        prompt = ChatPromptTemplate.from_messages([
            ("user", """
# 任务
从以下搜索结果中选择与主题最相关的 {max_urls} 个 URL。

# 主题: {topic}

# 已有信息: {summary_context}

# 搜索结果
{results}

# 输出
只输出选中的 URL 列表（每行一个）：
""")
        ])

        msg = prompt.format_messages(
            topic=topic,
            max_urls=max_urls,
            summary_context=summary_context[:1000] or "暂无",
            results="\n\n".join(formatted),
        )

        response = self.llm.invoke(msg, config=self.config)
        content = getattr(response, "content", "") or ""

        # Extract URLs from response
        urls = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("http"):
                if line not in self.selected_urls:
                    urls.append(line)

        # Fallback: use top scored results
        if not urls:
            sorted_results = sorted(available, key=lambda r: r.get("score", 0), reverse=True)
            urls = [r.get("url") for r in sorted_results[:max_urls] if r.get("url")]

        self.selected_urls.extend(urls[:max_urls])
        return urls[:max_urls]

    def summarize_findings(
        self,
        topic: str,
        results: List[Dict[str, Any]],
        existing_summary: str = "",
    ) -> str:
        """
        Summarize new findings from search results.

        Returns:
            Summary text
        """
        if not results:
            return ""

        formatted = []
        for i, r in enumerate(results[:10], 1):
            formatted.append(
                f"[{i}] {r.get('title', 'N/A')}\n"
                f"{(r.get('summary') or r.get('snippet') or r.get('raw_excerpt') or '')[:500]}"
            )

        prompt = ChatPromptTemplate.from_messages([
            ("user", """
# 任务
总结以下搜索结果中与主题相关的新发现。

# 主题: {topic}
# 已有信息: {existing_summary}
# 新搜索结果:
{findings}

# 输出要求
- 提取与主题相关的关键新信息
- 避免与已有信息重复
- 简洁有条理
- 500字以内
""")
        ])

        msg = prompt.format_messages(
            topic=topic,
            existing_summary=existing_summary[:1500] or "暂无",
            findings="\n\n".join(formatted),
        )

        response = self.llm.invoke(msg, config=self.config)
        return getattr(response, "content", "") or ""
