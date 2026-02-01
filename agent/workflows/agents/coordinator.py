"""
Research Coordinator Agent.

Inspired by DeerFlow's Coordinator pattern.
Orchestrates the research workflow, deciding when to gather more info vs. synthesize.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


class CoordinatorAction(str, Enum):
    """Actions the coordinator can take."""
    PLAN = "plan"           # Generate/refine research plan
    RESEARCH = "research"   # Gather more information
    SYNTHESIZE = "synthesize"  # Synthesize findings into report
    REFLECT = "reflect"     # Reflect on progress and strategy
    COMPLETE = "complete"   # Research is complete


COORDINATOR_PROMPT = """
# 角色
你是一名研究协调者，负责管理整个研究流程。你需要根据当前研究状态做出关键决策。

# 当前研究状态
- 主题: {topic}
- 已完成查询数: {num_queries}
- 已收集来源数: {num_sources}
- 已生成摘要数: {num_summaries}
- 当前轮次: {current_epoch}/{max_epochs}
- 已知信息摘要: {knowledge_summary}

# 你可以选择的行动
1. **plan**: 生成或优化研究计划（适用于研究初期或发现新方向时）
2. **research**: 继续收集更多信息（适用于信息不足时）
3. **synthesize**: 综合已有发现生成报告（适用于信息充足时）
4. **reflect**: 反思当前进展和策略（适用于进展缓慢或方向不明时）
5. **complete**: 完成研究（适用于信息充分、报告已生成时）

# 决策要求
根据当前状态选择最合适的下一步行动，并给出理由。

# 输出格式
严格按照以下格式输出：
action: <行动名称>
reasoning: <决策理由>
priority_topics: <如选择research，列出优先研究的子话题，逗号分隔>
"""


@dataclass
class CoordinatorDecision:
    """Decision made by the coordinator."""
    action: CoordinatorAction
    reasoning: str
    priority_topics: List[str]


class ResearchCoordinator:
    """
    Coordinates the research workflow.

    Decides the next step based on current research state:
    - How much information has been collected
    - Quality and coverage of existing findings
    - Research budget (epochs remaining)
    """

    def __init__(self, llm: BaseChatModel, config: Dict[str, Any] = None):
        self.llm = llm
        self.config = config or {}

    def decide_next_action(
        self,
        topic: str,
        num_queries: int,
        num_sources: int,
        num_summaries: int,
        current_epoch: int,
        max_epochs: int,
        knowledge_summary: str = "",
    ) -> CoordinatorDecision:
        """
        Decide the next action based on current research state.

        Returns:
            CoordinatorDecision with the chosen action
        """
        # Quick decision rules (no LLM needed)
        if current_epoch >= max_epochs:
            return CoordinatorDecision(
                action=CoordinatorAction.SYNTHESIZE,
                reasoning="已达到最大研究轮次，进入综合阶段",
                priority_topics=[],
            )

        if num_queries == 0:
            return CoordinatorDecision(
                action=CoordinatorAction.PLAN,
                reasoning="研究尚未开始，需要生成研究计划",
                priority_topics=[],
            )

        # Use LLM for complex decisions
        prompt = ChatPromptTemplate.from_messages([
            ("user", COORDINATOR_PROMPT)
        ])

        msg = prompt.format_messages(
            topic=topic,
            num_queries=num_queries,
            num_sources=num_sources,
            num_summaries=num_summaries,
            current_epoch=current_epoch,
            max_epochs=max_epochs,
            knowledge_summary=knowledge_summary[:2000] or "暂无",
        )

        response = self.llm.invoke(msg, config=self.config)
        content = getattr(response, "content", "") or ""

        return self._parse_decision(content)

    def _parse_decision(self, content: str) -> CoordinatorDecision:
        """Parse the coordinator's decision from LLM output."""
        action = CoordinatorAction.RESEARCH  # default
        reasoning = ""
        priority_topics = []

        for line in content.strip().split("\n"):
            line = line.strip()
            if line.lower().startswith("action:"):
                action_str = line.split(":", 1)[1].strip().lower()
                try:
                    action = CoordinatorAction(action_str)
                except ValueError:
                    action = CoordinatorAction.RESEARCH
            elif line.lower().startswith("reasoning:"):
                reasoning = line.split(":", 1)[1].strip()
            elif line.lower().startswith("priority_topics:"):
                topics_str = line.split(":", 1)[1].strip()
                priority_topics = [t.strip() for t in topics_str.split(",") if t.strip()]

        return CoordinatorDecision(
            action=action,
            reasoning=reasoning,
            priority_topics=priority_topics,
        )
