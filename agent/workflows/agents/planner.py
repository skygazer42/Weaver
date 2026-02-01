"""
Research Planner Agent.

Generates and refines structured research plans.
"""

import logging
from typing import Any, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

PLANNER_PROMPT = """
# 角色
你是一名研究规划专家，擅长为复杂话题制定全面的研究计划。

# 任务
为以下主题制定研究计划，生成结构化的搜索查询列表。

# 主题
{topic}

# 已有信息
{existing_knowledge}

# 已执行的查询
{existing_queries}

# 要求
1. 生成 {num_queries} 个搜索查询
2. 每个查询应覆盖主题的不同方面
3. 查询不能与已有查询重复
4. 查询应具体、有针对性
5. 考虑以下维度：定义、背景、核心内容、应用场景、优缺点、发展趋势、案例分析

# 输出格式
按优先级排序，每行一个查询。格式为 JSON 列表：
```json
[
    {{"query": "搜索查询1", "aspect": "覆盖的方面", "priority": 1}},
    {{"query": "搜索查询2", "aspect": "覆盖的方面", "priority": 2}}
]
```
"""


class ResearchPlanner:
    """
    Plans research by generating structured query sets.

    Responsibilities:
    - Decompose topics into searchable queries
    - Prioritize queries by importance
    - Refine plans based on findings
    """

    def __init__(self, llm: BaseChatModel, config: Dict[str, Any] = None):
        self.llm = llm
        self.config = config or {}

    def create_plan(
        self,
        topic: str,
        num_queries: int = 5,
        existing_knowledge: str = "",
        existing_queries: List[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Create a research plan.

        Returns:
            List of query dicts with 'query', 'aspect', 'priority'
        """
        import json

        prompt = ChatPromptTemplate.from_messages([
            ("user", PLANNER_PROMPT)
        ])

        msg = prompt.format_messages(
            topic=topic,
            existing_knowledge=existing_knowledge or "暂无",
            existing_queries=", ".join(existing_queries or []) or "无",
            num_queries=num_queries,
        )

        response = self.llm.invoke(msg, config=self.config)
        content = getattr(response, "content", "") or ""

        return self._parse_plan(content)

    def refine_plan(
        self,
        topic: str,
        gaps: List[str],
        existing_queries: List[str],
        num_queries: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Refine research plan based on identified knowledge gaps.

        Args:
            topic: Research topic
            gaps: Identified knowledge gaps
            existing_queries: Already executed queries
            num_queries: Number of new queries to generate

        Returns:
            List of new query dicts
        """
        gap_text = "\n".join(f"- {g}" for g in gaps) if gaps else "无明确缺口"

        prompt = ChatPromptTemplate.from_messages([
            ("user", """
# 任务
基于以下知识缺口，补充研究计划。

# 主题: {topic}

# 知识缺口
{gaps}

# 已有查询
{existing_queries}

# 要求
生成 {num_queries} 个针对知识缺口的搜索查询。

# 输出格式
```json
[{{"query": "查询", "aspect": "方面", "priority": 1}}]
```
""")
        ])

        msg = prompt.format_messages(
            topic=topic,
            gaps=gap_text,
            existing_queries=", ".join(existing_queries),
            num_queries=num_queries,
        )

        response = self.llm.invoke(msg, config=self.config)
        content = getattr(response, "content", "") or ""

        return self._parse_plan(content)

    def _parse_plan(self, content: str) -> List[Dict[str, Any]]:
        """Parse plan from LLM output."""
        import json
        import re

        # Find JSON in response
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content, re.I)
        if json_match:
            content = json_match.group(1)

        start = content.find("[")
        end = content.rfind("]") + 1
        if start >= 0 and end > start:
            content = content[start:end]

        try:
            data = json.loads(content)
            if isinstance(data, list):
                return [
                    {
                        "query": item.get("query", ""),
                        "aspect": item.get("aspect", ""),
                        "priority": item.get("priority", 99),
                    }
                    for item in data
                    if isinstance(item, dict) and item.get("query")
                ]
        except json.JSONDecodeError:
            pass

        # Fallback: extract lines as queries
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        return [{"query": line, "aspect": "", "priority": i} for i, line in enumerate(lines, 1)]
