"""
Research Compressor.

Compresses and structures research findings before report writing.
Inspired by Open Deep Research's fact extraction approach.

Key Features:
1. Extract key facts with source citations
2. Identify statistics and quantitative data
3. Remove redundancy and contradictions
4. Structure findings by subtopic
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


@dataclass
class ExtractedFact:
    """A single extracted fact with source."""
    fact: str
    source_url: str
    confidence: float = 0.8
    category: str = "general"


@dataclass
class CompressedKnowledge:
    """Structured compressed knowledge from research."""
    topic: str
    facts: List[ExtractedFact] = field(default_factory=list)
    statistics: List[Dict[str, Any]] = field(default_factory=list)
    key_entities: List[str] = field(default_factory=list)
    subtopics: Dict[str, List[ExtractedFact]] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "facts": [
                {"fact": f.fact, "source": f.source_url, "confidence": f.confidence, "category": f.category}
                for f in self.facts
            ],
            "statistics": self.statistics,
            "key_entities": self.key_entities,
            "subtopics": {
                k: [{"fact": f.fact, "source": f.source_url} for f in v]
                for k, v in self.subtopics.items()
            },
            "summary": self.summary,
        }


COMPRESSION_PROMPT = """
# 任务
分析以下研究内容，提取结构化的关键信息。

# 研究主题
{topic}

# 原始研究内容
{content}

# 要求
从内容中提取：
1. **关键事实** (facts): 核心事实陈述，标注来源URL和置信度
2. **统计数据** (statistics): 任何数字、百分比、数据
3. **关键实体** (key_entities): 重要的人名、公司、技术术语
4. **子话题分类** (subtopics): 按主题组织事实

# 输出格式
严格按以下JSON格式输出：
```json
{{
    "facts": [
        {{"fact": "事实陈述", "source": "来源URL", "confidence": 0.9, "category": "定义/背景/方法/应用/趋势"}}
    ],
    "statistics": [
        {{"metric": "指标名称", "value": "数值", "context": "上下文说明", "source": "来源URL"}}
    ],
    "key_entities": ["实体1", "实体2"],
    "subtopics": {{
        "子话题1": [
            {{"fact": "相关事实", "source": "来源URL"}}
        ]
    }},
    "summary": "50字以内的核心摘要"
}}
```
"""


class ResearchCompressor:
    """
    Compresses research content into structured facts.

    Reduces raw scraped content to essential facts with citations.
    """

    def __init__(self, llm: BaseChatModel, config: Dict[str, Any] = None):
        self.llm = llm
        self.config = config or {}

    def compress(
        self,
        topic: str,
        scraped_content: List[Dict[str, Any]],
        summary_notes: List[str] = None,
    ) -> CompressedKnowledge:
        """
        Compress research content into structured knowledge.

        Args:
            topic: Research topic
            scraped_content: List of search results with content
            summary_notes: Optional existing summary notes

        Returns:
            CompressedKnowledge object
        """
        # Build content string from scraped content
        content_parts = []

        for item in scraped_content:
            results = item.get("results", [])
            for r in results:
                url = r.get("url", "unknown")
                title = r.get("title", "")
                text = r.get("raw_excerpt") or r.get("summary") or r.get("snippet") or ""
                if text:
                    content_parts.append(f"[Source: {url}]\nTitle: {title}\n{text[:1500]}")

        # Add summary notes
        if summary_notes:
            content_parts.append("\n--- 已有摘要 ---\n" + "\n".join(summary_notes[:5]))

        if not content_parts:
            return CompressedKnowledge(topic=topic, summary="无研究内容可压缩")

        content_text = "\n\n---\n\n".join(content_parts[:20])  # Limit content size

        prompt = ChatPromptTemplate.from_messages([
            ("user", COMPRESSION_PROMPT)
        ])

        msg = prompt.format_messages(
            topic=topic,
            content=content_text,
        )

        response = self.llm.invoke(msg, config=self.config)
        content = getattr(response, "content", "") or ""

        return self._parse_response(topic, content)

    def _parse_response(self, topic: str, content: str) -> CompressedKnowledge:
        """Parse LLM response into CompressedKnowledge."""
        knowledge = CompressedKnowledge(topic=topic)

        # Extract JSON from response
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content, re.I)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON object directly
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
            else:
                knowledge.summary = content[:200]
                return knowledge

        try:
            data = json.loads(json_str)

            # Parse facts
            for f in data.get("facts", []):
                if isinstance(f, dict) and f.get("fact"):
                    knowledge.facts.append(ExtractedFact(
                        fact=f.get("fact", ""),
                        source_url=f.get("source", ""),
                        confidence=float(f.get("confidence", 0.8)),
                        category=f.get("category", "general"),
                    ))

            # Parse statistics
            knowledge.statistics = data.get("statistics", [])

            # Parse key entities
            knowledge.key_entities = data.get("key_entities", [])

            # Parse subtopics
            for subtopic, facts in data.get("subtopics", {}).items():
                knowledge.subtopics[subtopic] = []
                for f in facts:
                    if isinstance(f, dict) and f.get("fact"):
                        knowledge.subtopics[subtopic].append(ExtractedFact(
                            fact=f.get("fact", ""),
                            source_url=f.get("source", ""),
                        ))

            # Parse summary
            knowledge.summary = data.get("summary", "")

            logger.info(
                f"[Compressor] Extracted {len(knowledge.facts)} facts, "
                f"{len(knowledge.statistics)} stats, "
                f"{len(knowledge.subtopics)} subtopics"
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse compressor output: {e}")
            knowledge.summary = content[:200]

        return knowledge

    def merge_knowledge(
        self,
        existing: CompressedKnowledge,
        new: CompressedKnowledge,
    ) -> CompressedKnowledge:
        """
        Merge two CompressedKnowledge objects, removing duplicates.

        Args:
            existing: Existing knowledge
            new: New knowledge to merge

        Returns:
            Merged CompressedKnowledge
        """
        merged = CompressedKnowledge(topic=existing.topic)

        # Merge facts (deduplicate by fact text similarity)
        seen_facts = set()
        for f in existing.facts + new.facts:
            fact_key = f.fact[:100].lower().strip()
            if fact_key not in seen_facts:
                merged.facts.append(f)
                seen_facts.add(fact_key)

        # Merge statistics
        merged.statistics = existing.statistics + new.statistics

        # Merge key entities
        merged.key_entities = list(set(existing.key_entities + new.key_entities))

        # Merge subtopics
        merged.subtopics = {**existing.subtopics}
        for k, v in new.subtopics.items():
            if k in merged.subtopics:
                merged.subtopics[k].extend(v)
            else:
                merged.subtopics[k] = v

        # Keep newer summary
        merged.summary = new.summary or existing.summary

        return merged

    def to_writer_context(self, knowledge: CompressedKnowledge) -> str:
        """
        Convert CompressedKnowledge to context string for writer.

        Args:
            knowledge: Compressed knowledge object

        Returns:
            Formatted context string
        """
        parts = [f"# 研究主题: {knowledge.topic}\n"]

        if knowledge.summary:
            parts.append(f"## 核心摘要\n{knowledge.summary}\n")

        if knowledge.facts:
            parts.append("## 关键事实")
            for i, f in enumerate(knowledge.facts, 1):
                parts.append(f"{i}. {f.fact} [来源: {f.source_url}] (置信度: {f.confidence:.0%})")
            parts.append("")

        if knowledge.statistics:
            parts.append("## 统计数据")
            for s in knowledge.statistics:
                parts.append(f"- {s.get('metric', 'N/A')}: {s.get('value', 'N/A')} ({s.get('context', '')})")
            parts.append("")

        if knowledge.key_entities:
            parts.append(f"## 关键实体\n{', '.join(knowledge.key_entities)}\n")

        if knowledge.subtopics:
            parts.append("## 子话题")
            for subtopic, facts in knowledge.subtopics.items():
                parts.append(f"### {subtopic}")
                for f in facts:
                    parts.append(f"- {f.fact}")
            parts.append("")

        return "\n".join(parts)
