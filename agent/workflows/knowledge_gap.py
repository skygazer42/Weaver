"""
IterDRAG Knowledge Gap Analysis.

Inspired by Local Deep Researcher's iterative approach.
Analyzes what knowledge gaps remain after each search iteration
and generates targeted queries to fill them.

Key Features:
1. Gap detection after each research iteration
2. Targeted query generation for missing information
3. Coverage tracking per sub-topic
4. Confidence scoring for knowledge completeness
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


GAP_ANALYSIS_PROMPT = """
# 角色
你是一名研究质量分析专家，擅长识别知识盲区和信息缺口。

# 任务
分析以下研究主题和已收集的信息，识别仍然存在的知识缺口。

# 研究主题
{topic}

# 研究目标（主题应该涵盖的方面）
- 定义和概念解释
- 历史背景和发展
- 核心内容和关键要素
- 应用场景和实际案例
- 优缺点分析
- 与相关主题的比较
- 未来趋势和展望
- 专家观点和数据支持

# 已执行的查询
{executed_queries}

# 已收集的信息摘要
{collected_knowledge}

# 输出要求
分析信息完整性，输出 JSON 格式结果：
```json
{{
    "overall_coverage": 0.65,
    "confidence": 0.7,
    "gaps": [
        {{"aspect": "缺失的方面", "importance": "high/medium/low", "reason": "为什么这个方面重要"}},
    ],
    "suggested_queries": [
        "针对缺口1的搜索查询",
        "针对缺口2的搜索查询"
    ],
    "covered_aspects": ["已覆盖的方面1", "已覆盖的方面2"],
    "analysis": "整体分析说明"
}}
```

# 注意
- overall_coverage: 0-1，表示主题覆盖程度
- confidence: 0-1，表示对分析结果的置信度
- 只列出真正重要的缺口，不要过度生成
- suggested_queries 应该具体、可操作
"""


@dataclass
class KnowledgeGap:
    """A identified knowledge gap."""
    aspect: str
    importance: str  # high, medium, low
    reason: str


@dataclass
class GapAnalysisResult:
    """Result of knowledge gap analysis."""
    overall_coverage: float
    confidence: float
    gaps: List[KnowledgeGap]
    suggested_queries: List[str]
    covered_aspects: List[str]
    analysis: str
    is_sufficient: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GapAnalysisResult":
        gaps = []
        for g in data.get("gaps", []):
            if isinstance(g, dict):
                gaps.append(KnowledgeGap(
                    aspect=g.get("aspect", ""),
                    importance=g.get("importance", "medium"),
                    reason=g.get("reason", ""),
                ))

        coverage = float(data.get("overall_coverage", 0.5))

        return cls(
            overall_coverage=coverage,
            confidence=float(data.get("confidence", 0.5)),
            gaps=gaps,
            suggested_queries=data.get("suggested_queries", []),
            covered_aspects=data.get("covered_aspects", []),
            analysis=data.get("analysis", ""),
            is_sufficient=coverage >= 0.8 and len(gaps) == 0,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_coverage": self.overall_coverage,
            "confidence": self.confidence,
            "gaps": [{"aspect": g.aspect, "importance": g.importance, "reason": g.reason} for g in self.gaps],
            "suggested_queries": self.suggested_queries,
            "covered_aspects": self.covered_aspects,
            "analysis": self.analysis,
            "is_sufficient": self.is_sufficient,
        }


class KnowledgeGapAnalyzer:
    """
    Analyzes research findings to identify knowledge gaps.

    Implements the IterDRAG pattern:
    1. Decomposition: Break down topic into aspects
    2. Retrieval: Search for information (external)
    3. Aggregation: Collect findings
    4. Gap Analysis: Identify what's missing
    """

    def __init__(
        self,
        llm: BaseChatModel,
        config: Dict[str, Any] = None,
        coverage_threshold: float = 0.8,
    ):
        """
        Initialize the analyzer.

        Args:
            llm: Language model for analysis
            config: LangChain config
            coverage_threshold: Minimum coverage to consider research sufficient
        """
        self.llm = llm
        self.config = config or {}
        self.coverage_threshold = coverage_threshold
        self.history: List[GapAnalysisResult] = []

    def analyze(
        self,
        topic: str,
        executed_queries: List[str],
        collected_knowledge: str,
    ) -> GapAnalysisResult:
        """
        Analyze the current state of research and identify gaps.

        Args:
            topic: Research topic
            executed_queries: List of queries already executed
            collected_knowledge: Summary of collected information

        Returns:
            GapAnalysisResult with gaps and suggested queries
        """
        prompt = ChatPromptTemplate.from_messages([
            ("user", GAP_ANALYSIS_PROMPT)
        ])

        msg = prompt.format_messages(
            topic=topic,
            executed_queries=", ".join(executed_queries) if executed_queries else "暂无",
            collected_knowledge=collected_knowledge[:4000] if collected_knowledge else "暂无收集的信息",
        )

        response = self.llm.invoke(msg, config=self.config)
        content = getattr(response, "content", "") or ""

        result = self._parse_result(content)
        self.history.append(result)

        logger.info(
            f"[GapAnalyzer] Coverage: {result.overall_coverage:.2f}, "
            f"Gaps: {len(result.gaps)}, "
            f"Queries suggested: {len(result.suggested_queries)}"
        )

        return result

    def _parse_result(self, content: str) -> GapAnalysisResult:
        """Parse LLM output into GapAnalysisResult."""
        # Find JSON in response
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content, re.I)
        if json_match:
            content = json_match.group(1)

        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            content = content[start:end]

        try:
            data = json.loads(content)
            return GapAnalysisResult.from_dict(data)
        except json.JSONDecodeError:
            logger.warning(f"[GapAnalyzer] Failed to parse JSON: {content[:200]}...")
            return GapAnalysisResult(
                overall_coverage=0.5,
                confidence=0.3,
                gaps=[],
                suggested_queries=[],
                covered_aspects=[],
                analysis="Failed to parse analysis result",
                is_sufficient=False,
            )

    def get_priority_queries(
        self,
        result: GapAnalysisResult,
        max_queries: int = 3,
    ) -> List[str]:
        """
        Get prioritized queries based on gap importance.

        Args:
            result: Gap analysis result
            max_queries: Maximum number of queries to return

        Returns:
            List of prioritized queries
        """
        # Sort gaps by importance
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_gaps = sorted(
            result.gaps,
            key=lambda g: priority_order.get(g.importance.lower(), 1),
        )

        # Map gaps to suggested queries
        queries = []
        for gap in sorted_gaps:
            # Find a query that matches this gap
            for query in result.suggested_queries:
                if gap.aspect.lower() in query.lower() or query not in queries:
                    queries.append(query)
                    break

            if len(queries) >= max_queries:
                break

        # Fill with remaining suggested queries if needed
        for query in result.suggested_queries:
            if query not in queries:
                queries.append(query)
            if len(queries) >= max_queries:
                break

        return queries[:max_queries]

    def is_research_sufficient(self, result: GapAnalysisResult = None) -> bool:
        """
        Check if research is sufficient based on latest analysis.

        Returns:
            True if coverage meets threshold and no high-priority gaps
        """
        if result is None:
            result = self.history[-1] if self.history else None

        if result is None:
            return False

        has_high_priority_gaps = any(
            g.importance.lower() == "high" for g in result.gaps
        )

        return (
            result.overall_coverage >= self.coverage_threshold and
            not has_high_priority_gaps
        )

    def get_coverage_trend(self) -> List[float]:
        """Get the trend of coverage across analysis iterations."""
        return [r.overall_coverage for r in self.history]

    def summarize_remaining_gaps(self) -> str:
        """Get a summary of all remaining gaps from latest analysis."""
        if not self.history:
            return "No analysis performed yet."

        latest = self.history[-1]
        if not latest.gaps:
            return "No significant gaps identified."

        lines = ["Remaining knowledge gaps:"]
        for i, gap in enumerate(latest.gaps, 1):
            lines.append(f"{i}. [{gap.importance.upper()}] {gap.aspect}: {gap.reason}")

        return "\n".join(lines)

    def generate_targeted_queries(
        self,
        result: Optional[GapAnalysisResult] = None,
        max_queries: int = 5,
    ) -> List[str]:
        """
        Generate targeted search queries based on identified knowledge gaps.

        This is designed for integration with deepsearch's query generation loop.
        Returns queries that directly address the most important gaps.

        Args:
            result: Gap analysis result (uses latest if None)
            max_queries: Maximum number of queries to generate

        Returns:
            List of targeted search queries
        """
        if result is None:
            result = self.history[-1] if self.history else None

        if result is None or not result.gaps:
            return []

        # Start with suggested queries from the analysis
        targeted = list(result.suggested_queries)

        # If we don't have enough, generate from gaps directly
        if len(targeted) < max_queries:
            for gap in result.gaps:
                if len(targeted) >= max_queries:
                    break
                # Create a query from the gap aspect
                gap_query = gap.aspect
                if gap_query not in targeted:
                    targeted.append(gap_query)

        return targeted[:max_queries]

    def get_high_priority_aspects(
        self,
        result: Optional[GapAnalysisResult] = None,
    ) -> List[str]:
        """
        Get list of high-priority missing aspects.

        Useful for biasing query generation toward critical gaps.

        Args:
            result: Gap analysis result (uses latest if None)

        Returns:
            List of high-priority aspect strings
        """
        if result is None:
            result = self.history[-1] if self.history else None

        if result is None:
            return []

        return [
            gap.aspect
            for gap in result.gaps
            if gap.importance.lower() == "high"
        ]


def integrate_gap_analysis(
    topic: str,
    llm: BaseChatModel,
    current_queries: List[str],
    current_summaries: List[str],
    config: Dict[str, Any] = None,
    max_new_queries: int = 3,
) -> Tuple[List[str], bool]:
    """
    Convenience function to integrate gap analysis into research loop.

    Args:
        topic: Research topic
        llm: Language model for analysis
        current_queries: Already executed queries
        current_summaries: Collected knowledge summaries
        config: LangChain config
        max_new_queries: Maximum new queries to generate

    Returns:
        Tuple of (new_queries, is_sufficient)
    """
    analyzer = KnowledgeGapAnalyzer(llm, config)

    collected_knowledge = "\n\n".join(current_summaries)
    result = analyzer.analyze(topic, current_queries, collected_knowledge)

    new_queries = analyzer.get_priority_queries(result, max_new_queries)
    is_sufficient = analyzer.is_research_sufficient(result)

    return new_queries, is_sufficient
