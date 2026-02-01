"""
Research Reporter Agent.

Synthesizes research findings into comprehensive reports.
"""

import logging
from typing import Any, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


REPORTER_PROMPT = """
# 角色
你是一名专业的研究报告撰写者。基于收集的研究发现，撰写一份全面的深度研究报告。

# 主题
{topic}

# 研究发现
{findings}

# 来源列表
{sources}

# 报告要求
## 内容要求
- 字数不少于 3500 字，尽可能详细全面
- 所有事实、数据必须来自提供的信息
- 涵盖主题的所有关键方面
- 提供足够的技术深度和专业见解
- 引用具体数据和案例

## 结构要求
- 使用清晰的 Markdown 标题层级（# ## ###）
- 逻辑清晰，层次分明
- 每段内容聚焦单一要点
- 适当使用项目符号和编号列表

## 格式要求
- 直接以 Markdown 格式输出
- 在文末添加"参考来源"部分
- 使用 [来源序号] 格式进行行内引用

# 输出结构
1. 概述/摘要
2. 核心内容（多个章节）
3. 分析与见解
4. 结论与展望
5. 参考来源
"""


class ResearchReporter:
    """
    Synthesizes research findings into comprehensive reports.

    Responsibilities:
    - Aggregate and organize findings
    - Write structured reports
    - Ensure citation accuracy
    - Review and refine reports
    """

    def __init__(self, llm: BaseChatModel, config: Dict[str, Any] = None):
        self.llm = llm
        self.config = config or {}

    def generate_report(
        self,
        topic: str,
        findings: List[str],
        sources: List[str],
    ) -> str:
        """
        Generate a comprehensive research report.

        Args:
            topic: Research topic
            findings: List of research finding summaries
            sources: List of source URLs

        Returns:
            Markdown formatted report
        """
        # Format sources with indices
        sources_text = "\n".join(
            f"[{i}] {url}" for i, url in enumerate(sources, 1)
        ) if sources else "无来源"

        findings_text = "\n\n---\n\n".join(findings) if findings else "暂无发现"

        prompt = ChatPromptTemplate.from_messages([
            ("user", REPORTER_PROMPT)
        ])

        msg = prompt.format_messages(
            topic=topic,
            findings=findings_text,
            sources=sources_text,
        )

        response = self.llm.invoke(msg, config=self.config)
        report = getattr(response, "content", "") or ""

        logger.info(f"[Reporter] Generated report: {len(report)} chars")
        return report

    def refine_report(
        self,
        report: str,
        feedback: str,
        topic: str,
    ) -> str:
        """
        Refine a report based on feedback.

        Args:
            report: Original report
            feedback: Evaluation feedback
            topic: Research topic

        Returns:
            Refined report
        """
        prompt = ChatPromptTemplate.from_messages([
            ("user", """
# 任务
根据评审反馈修改研究报告。

# 主题: {topic}

# 当前报告
{report}

# 评审反馈
{feedback}

# 要求
1. 根据反馈修改相应内容
2. 保持报告的整体结构和风格
3. 确保修改后的内容准确无误
4. 输出完整的修改后报告（Markdown 格式）
""")
        ])

        msg = prompt.format_messages(
            topic=topic,
            report=report,
            feedback=feedback,
        )

        response = self.llm.invoke(msg, config=self.config)
        refined = getattr(response, "content", "") or ""

        logger.info(f"[Reporter] Refined report: {len(refined)} chars")
        return refined if refined else report

    def generate_executive_summary(
        self,
        report: str,
        topic: str,
    ) -> str:
        """
        Generate an executive summary for the report.

        Returns:
            Executive summary text
        """
        prompt = ChatPromptTemplate.from_messages([
            ("user", """
# 任务
为以下研究报告生成执行摘要。

# 主题: {topic}

# 报告
{report}

# 要求
- 300字以内
- 包含核心发现、关键结论和建议
- 简洁明了，高度概括
""")
        ])

        msg = prompt.format_messages(
            topic=topic,
            report=report[:5000],
        )

        response = self.llm.invoke(msg, config=self.config)
        return getattr(response, "content", "") or ""
