"""
Tree-based Deep Research Implementation.

Inspired by GPT Researcher's tree exploration approach.
Replaces linear multi-epoch method with tree-based topic decomposition
and parallel exploration of sub-topics.

Key Features:
1. Topic decomposition into sub-topics (tree structure)
2. Parallel exploration of branches
3. Intelligent branch merging
4. Depth-limited exploration with breadth control
"""

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from common.cancellation import check_cancellation as _check_cancel_token
from common.config import settings

logger = logging.getLogger(__name__)


class NodeStatus(str, Enum):
    """Status of a research tree node."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ResearchTreeNode:
    """
    A node in the research tree representing a topic or sub-topic.

    Attributes:
        id: Unique identifier for this node
        topic: The topic/query this node explores
        depth: Depth in the tree (0 = root)
        parent_id: Parent node's ID (None for root)
        children_ids: List of child node IDs
        status: Current exploration status
        findings: Collected research findings
        sources: URLs and sources found
        summary: Synthesized summary of findings
        queries: Search queries generated for this topic
        relevance_score: How relevant this branch is (0-1)
        created_at: Timestamp of node creation
        completed_at: Timestamp of completion
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    topic: str = ""
    depth: int = 0
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    findings: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    summary: str = ""
    queries: List[str] = field(default_factory=list)
    relevance_score: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary for serialization."""
        return {
            "id": self.id,
            "topic": self.topic,
            "depth": self.depth,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids,
            "status": self.status.value,
            "findings_count": len(self.findings),
            "sources_count": len(self.sources),
            "summary_length": len(self.summary),
            "queries": self.queries,
            "relevance_score": self.relevance_score,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    def mark_complete(self, summary: str = "") -> None:
        """Mark this node as completed."""
        self.status = NodeStatus.COMPLETED
        self.completed_at = datetime.now().isoformat()
        if summary:
            self.summary = summary

    def mark_failed(self, error: str = "") -> None:
        """Mark this node as failed."""
        self.status = NodeStatus.FAILED
        self.completed_at = datetime.now().isoformat()
        if error:
            self.summary = f"[FAILED] {error}"


@dataclass
class ResearchTree:
    """
    A tree structure for organizing hierarchical research.

    The tree starts with a root topic and branches into sub-topics,
    each explored in parallel up to a configurable depth.
    """
    root_id: Optional[str] = None
    nodes: Dict[str, ResearchTreeNode] = field(default_factory=dict)
    max_depth: int = 2
    max_branches: int = 4
    total_sources: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def create_root(self, topic: str) -> ResearchTreeNode:
        """Create the root node of the research tree."""
        root = ResearchTreeNode(
            topic=topic,
            depth=0,
            parent_id=None,
        )
        self.root_id = root.id
        self.nodes[root.id] = root
        logger.info(f"[ResearchTree] Created root node: {root.id} - '{topic}'")
        return root

    def add_child(self, parent_id: str, topic: str, relevance_score: float = 1.0) -> Optional[ResearchTreeNode]:
        """Add a child node to the specified parent."""
        parent = self.nodes.get(parent_id)
        if not parent:
            logger.warning(f"[ResearchTree] Parent node {parent_id} not found")
            return None

        # Check depth limit
        if parent.depth >= self.max_depth:
            logger.info(f"[ResearchTree] Max depth {self.max_depth} reached, skipping child")
            return None

        # Check branch limit
        if len(parent.children_ids) >= self.max_branches:
            logger.info(f"[ResearchTree] Max branches {self.max_branches} reached for parent {parent_id}")
            return None

        child = ResearchTreeNode(
            topic=topic,
            depth=parent.depth + 1,
            parent_id=parent_id,
            relevance_score=relevance_score,
        )
        self.nodes[child.id] = child
        parent.children_ids.append(child.id)

        logger.info(f"[ResearchTree] Added child node: {child.id} - '{topic}' (depth={child.depth})")
        return child

    def get_node(self, node_id: str) -> Optional[ResearchTreeNode]:
        """Get a node by its ID."""
        return self.nodes.get(node_id)

    def get_root(self) -> Optional[ResearchTreeNode]:
        """Get the root node."""
        return self.nodes.get(self.root_id) if self.root_id else None

    def get_children(self, node_id: str) -> List[ResearchTreeNode]:
        """Get all children of a node."""
        node = self.nodes.get(node_id)
        if not node:
            return []
        return [self.nodes[cid] for cid in node.children_ids if cid in self.nodes]

    def get_pending_nodes(self) -> List[ResearchTreeNode]:
        """Get all nodes with pending status."""
        return [n for n in self.nodes.values() if n.status == NodeStatus.PENDING]

    def get_completed_nodes(self) -> List[ResearchTreeNode]:
        """Get all completed nodes."""
        return [n for n in self.nodes.values() if n.status == NodeStatus.COMPLETED]

    def get_nodes_at_depth(self, depth: int) -> List[ResearchTreeNode]:
        """Get all nodes at a specific depth."""
        return [n for n in self.nodes.values() if n.depth == depth]

    def get_all_sources(self) -> List[str]:
        """Get all unique sources from all nodes."""
        sources = set()
        for node in self.nodes.values():
            sources.update(node.sources)
        return list(sources)

    def get_all_findings(self) -> List[Dict[str, Any]]:
        """Get all findings from all nodes."""
        findings = []
        for node in self.get_completed_nodes():
            findings.extend(node.findings)
        return findings

    def get_merged_summary(self) -> str:
        """Get merged summary from all completed nodes, organized hierarchically."""
        lines = []

        def _traverse(node_id: str, indent: int = 0) -> None:
            node = self.nodes.get(node_id)
            if not node or node.status != NodeStatus.COMPLETED:
                return

            prefix = "  " * indent
            lines.append(f"{prefix}## {node.topic}")
            if node.summary:
                lines.append(f"{prefix}{node.summary}")
            lines.append("")

            for child_id in node.children_ids:
                _traverse(child_id, indent + 1)

        if self.root_id:
            _traverse(self.root_id)

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert tree to dictionary for serialization."""
        return {
            "root_id": self.root_id,
            "max_depth": self.max_depth,
            "max_branches": self.max_branches,
            "total_nodes": len(self.nodes),
            "total_sources": len(self.get_all_sources()),
            "completed_nodes": len(self.get_completed_nodes()),
            "pending_nodes": len(self.get_pending_nodes()),
            "created_at": self.created_at,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
        }


# Prompt for decomposing a topic into sub-topics
DECOMPOSE_TOPIC_PROMPT = """
# 角色
你是一名研究专家，擅长将复杂话题分解为更具体的子话题进行深入研究。

# 任务
将以下主题分解为 {num_subtopics} 个有价值的子话题，每个子话题应该：
1. 与主话题高度相关
2. 足够具体，可以单独进行深入研究
3. 互不重叠，覆盖主题的不同方面
4. 具有研究价值，能找到有用信息

# 主题
{topic}

# 已知信息
{existing_knowledge}

# 输出格式
严格按照 JSON 格式输出，包含子话题列表和每个子话题的相关性评分（0-1）：
```json
{{
    "subtopics": [
        {{"topic": "子话题1", "relevance": 0.9, "reason": "为什么这个子话题重要"}},
        {{"topic": "子话题2", "relevance": 0.85, "reason": "为什么这个子话题重要"}}
    ]
}}
```

# 注意事项
- 子话题数量应为 {num_subtopics} 个
- 每个子话题应该比原主题更具体
- 避免重复或过于相似的子话题
- 考虑不同的研究角度（定义、历史、应用、比较、未来趋势等）
"""


def _parse_json_output(text: str) -> Dict[str, Any]:
    """Parse JSON output from LLM response."""
    if not text:
        return {}

    # Try to find JSON in code blocks
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.I)
    if json_match:
        text = json_match.group(1)

    # Try to find JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"[ResearchTree] Failed to parse JSON: {text[:200]}...")
        return {}


class TreeExplorer:
    """
    Explores a research tree by decomposing topics and gathering findings.

    This class orchestrates the tree-based research process:
    1. Decompose the root topic into sub-topics
    2. Explore each branch (sub-topic) in parallel
    3. Merge findings from all branches
    4. Generate final synthesis
    """

    def __init__(
        self,
        planner_llm: ChatOpenAI,
        researcher_llm: ChatOpenAI,
        writer_llm: ChatOpenAI,
        search_func,  # Function to perform search (e.g., tavily_search.invoke)
        config: Dict[str, Any] = None,
        max_depth: int = 2,
        max_branches: int = 4,
        queries_per_branch: int = 3,
    ):
        """
        Initialize the TreeExplorer.

        Args:
            planner_llm: LLM for planning and decomposition
            researcher_llm: LLM for analyzing search results
            writer_llm: LLM for synthesis and writing
            search_func: Function to perform web search
            config: LangChain config dict
            max_depth: Maximum tree depth (0 = root only)
            max_branches: Maximum children per node
            queries_per_branch: Number of queries per branch
        """
        self.planner_llm = planner_llm
        self.researcher_llm = researcher_llm
        self.writer_llm = writer_llm
        self.search_func = search_func
        self.config = config or {}
        self.max_depth = max_depth
        self.max_branches = max_branches
        self.queries_per_branch = queries_per_branch

        self.tree: Optional[ResearchTree] = None
        self.all_searched_urls: List[str] = []
        self.start_time: float = 0

    def _check_cancel(self, state: Dict[str, Any]) -> None:
        """Check for cancellation."""
        if state.get("is_cancelled"):
            raise asyncio.CancelledError("Task was cancelled (flag)")
        token_id = state.get("cancel_token_id")
        if token_id:
            _check_cancel_token(token_id)

    def decompose_topic(
        self,
        topic: str,
        existing_knowledge: str = "",
        num_subtopics: int = 4,
    ) -> List[Tuple[str, float]]:
        """
        Decompose a topic into sub-topics.

        Args:
            topic: The topic to decompose
            existing_knowledge: Already known information
            num_subtopics: Number of sub-topics to generate

        Returns:
            List of (subtopic, relevance_score) tuples
        """
        prompt = ChatPromptTemplate.from_messages([
            ("user", DECOMPOSE_TOPIC_PROMPT)
        ])

        msg = prompt.format_messages(
            topic=topic,
            existing_knowledge=existing_knowledge or "暂无",
            num_subtopics=num_subtopics,
        )

        response = self.planner_llm.invoke(msg, config=self.config)
        content = getattr(response, "content", "") or ""

        parsed = _parse_json_output(content)
        subtopics = parsed.get("subtopics", [])

        result = []
        for item in subtopics:
            if isinstance(item, dict):
                topic_text = item.get("topic", "")
                relevance = float(item.get("relevance", 0.8))
                if topic_text:
                    result.append((topic_text, relevance))

        logger.info(f"[TreeExplorer] Decomposed into {len(result)} subtopics")
        return result[:num_subtopics]

    def explore_branch(
        self,
        node: ResearchTreeNode,
        state: Dict[str, Any],
        per_query_results: int = 5,
    ) -> None:
        """
        Explore a single branch (node) of the research tree.

        Args:
            node: The node to explore
            state: Agent state for cancellation checking
            per_query_results: Results per search query
        """
        self._check_cancel(state)

        node.status = NodeStatus.IN_PROGRESS
        logger.info(f"[TreeExplorer] Exploring branch: {node.id} - '{node.topic}'")

        try:
            # Generate queries for this topic
            from prompts.templates.deepsearch import formulate_query_prompt

            prompt = ChatPromptTemplate.from_messages([
                ("user", formulate_query_prompt)
            ])

            msg = prompt.format_messages(
                topic=node.topic,
                have_query=", ".join(node.queries) or "[]",
                summary_search=node.summary or "暂无",
                query_num=self.queries_per_branch,
            )

            response = self.planner_llm.invoke(msg, config=self.config)
            queries = self._parse_list_output(getattr(response, "content", ""))

            # Add original topic as a query if not present
            if node.topic not in queries:
                queries.insert(0, node.topic)

            node.queries = queries[:self.queries_per_branch]
            logger.info(f"[TreeExplorer] Generated {len(node.queries)} queries for branch {node.id}")

            # Execute searches
            for query in node.queries:
                self._check_cancel(state)

                results = self.search_func(
                    {"query": query, "max_results": per_query_results},
                    config=self.config,
                )

                for r in results:
                    url = r.get("url")
                    if url and url not in self.all_searched_urls:
                        self.all_searched_urls.append(url)
                        node.sources.append(url)
                    node.findings.append({
                        "query": query,
                        "result": r,
                        "timestamp": datetime.now().isoformat(),
                    })

            # Summarize findings
            if node.findings:
                node.summary = self._summarize_branch(node)

            node.mark_complete()
            logger.info(f"[TreeExplorer] Completed branch {node.id}: {len(node.findings)} findings, {len(node.sources)} sources")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[TreeExplorer] Failed to explore branch {node.id}: {e}")
            node.mark_failed(str(e))

    def _summarize_branch(self, node: ResearchTreeNode) -> str:
        """Summarize the findings of a branch."""
        findings_text = []
        for i, f in enumerate(node.findings[:10], 1):  # Limit to first 10
            r = f.get("result", {})
            findings_text.append(
                f"[{i}] {r.get('title', 'N/A')}\n"
                f"URL: {r.get('url', '')}\n"
                f"摘要: {r.get('summary', r.get('snippet', ''))[:500]}"
            )

        prompt = ChatPromptTemplate.from_messages([
            ("user", """
# 任务
总结以下搜索结果中与主题相关的关键信息。

# 主题
{topic}

# 搜索结果
{findings}

# 输出要求
- 提取关键信息和洞见
- 保持简洁，500字以内
- 使用要点列表格式
- 标注重要来源
""")
        ])

        msg = prompt.format_messages(
            topic=node.topic,
            findings="\n\n".join(findings_text),
        )

        response = self.researcher_llm.invoke(msg, config=self.config)
        return getattr(response, "content", "") or ""

    def merge_branches(self, nodes: List[ResearchTreeNode]) -> str:
        """
        Merge findings from multiple branches into a coherent summary.

        Args:
            nodes: List of completed nodes to merge

        Returns:
            Merged summary text
        """
        if not nodes:
            return ""

        branch_summaries = []
        for node in nodes:
            if node.status == NodeStatus.COMPLETED and node.summary:
                branch_summaries.append(f"## {node.topic}\n{node.summary}")

        if not branch_summaries:
            return ""

        prompt = ChatPromptTemplate.from_messages([
            ("user", """
# 任务
整合以下各分支的研究发现，生成一份统一的研究摘要。

# 各分支发现
{branch_summaries}

# 输出要求
- 整合所有分支的关键发现
- 识别共同主题和差异
- 按逻辑顺序组织内容
- 保留重要细节和来源
- 字数不超过1000字
""")
        ])

        msg = prompt.format_messages(
            branch_summaries="\n\n".join(branch_summaries),
        )

        response = self.writer_llm.invoke(msg, config=self.config)
        return getattr(response, "content", "") or ""

    def run(
        self,
        topic: str,
        state: Dict[str, Any],
        decompose_root: bool = True,
    ) -> ResearchTree:
        """
        Run the tree-based research process.

        Args:
            topic: The main topic to research
            state: Agent state for cancellation checking
            decompose_root: Whether to decompose root into subtopics

        Returns:
            The completed ResearchTree
        """
        self.start_time = time.time()
        self._check_cancel(state)

        # Initialize tree
        self.tree = ResearchTree(
            max_depth=self.max_depth,
            max_branches=self.max_branches,
        )

        # Create root
        root = self.tree.create_root(topic)

        # Explore root first
        logger.info(f"[TreeExplorer] Starting tree exploration for: {topic}")
        self.explore_branch(root, state)

        # Decompose and explore sub-topics if enabled
        if decompose_root and self.max_depth > 0:
            self._check_cancel(state)

            # Decompose into subtopics
            subtopics = self.decompose_topic(
                topic,
                existing_knowledge=root.summary,
                num_subtopics=self.max_branches,
            )

            # Create child nodes
            for subtopic, relevance in subtopics:
                child = self.tree.add_child(root.id, subtopic, relevance)
                if child:
                    self._check_cancel(state)
                    self.explore_branch(child, state)

                    # Recursively explore if depth allows
                    if child.depth < self.max_depth:
                        self._explore_children(child, state)

        elapsed = time.time() - self.start_time
        logger.info(
            f"[TreeExplorer] Completed tree exploration in {elapsed:.2f}s\n"
            f"  Total nodes: {len(self.tree.nodes)}\n"
            f"  Completed: {len(self.tree.get_completed_nodes())}\n"
            f"  Total sources: {len(self.all_searched_urls)}"
        )

        return self.tree

    def _explore_children(self, parent: ResearchTreeNode, state: Dict[str, Any]) -> None:
        """Recursively explore children of a node (synchronous version)."""
        if parent.depth >= self.max_depth:
            return

        # Decompose this node's topic
        subtopics = self.decompose_topic(
            parent.topic,
            existing_knowledge=parent.summary,
            num_subtopics=min(2, self.max_branches),  # Fewer children at deeper levels
        )

        for subtopic, relevance in subtopics:
            child = self.tree.add_child(parent.id, subtopic, relevance)
            if child:
                self._check_cancel(state)
                self.explore_branch(child, state)

    # ==================== Async Parallel Exploration ====================

    async def explore_branch_async(
        self,
        node: ResearchTreeNode,
        state: Dict[str, Any],
        per_query_results: int = 5,
    ) -> None:
        """
        Async version of explore_branch for parallel execution.

        Args:
            node: The node to explore
            state: Agent state for cancellation checking
            per_query_results: Results per search query
        """
        self._check_cancel(state)

        node.status = NodeStatus.IN_PROGRESS
        logger.info(f"[TreeExplorer] Async exploring branch: {node.id} - '{node.topic}'")

        try:
            # Generate queries for this topic
            from prompts.templates.deepsearch import formulate_query_prompt

            prompt = ChatPromptTemplate.from_messages([
                ("user", formulate_query_prompt)
            ])

            msg = prompt.format_messages(
                topic=node.topic,
                have_query=", ".join(node.queries) or "[]",
                summary_search=node.summary or "暂无",
                query_num=self.queries_per_branch,
            )

            # Run LLM call in executor to not block event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.planner_llm.invoke(msg, config=self.config)
            )
            queries = self._parse_list_output(getattr(response, "content", ""))

            # Add original topic as a query if not present
            if node.topic not in queries:
                queries.insert(0, node.topic)

            node.queries = queries[:self.queries_per_branch]
            logger.info(f"[TreeExplorer] Generated {len(node.queries)} queries for branch {node.id}")

            # Execute searches (in executor)
            for query in node.queries:
                self._check_cancel(state)

                results = await loop.run_in_executor(
                    None,
                    lambda q=query: self.search_func(
                        {"query": q, "max_results": per_query_results},
                        config=self.config,
                    )
                )

                for r in results:
                    url = r.get("url")
                    if url and url not in self.all_searched_urls:
                        self.all_searched_urls.append(url)
                        node.sources.append(url)
                    node.findings.append({
                        "query": query,
                        "result": r,
                        "timestamp": datetime.now().isoformat(),
                    })

            # Summarize findings (in executor)
            if node.findings:
                node.summary = await loop.run_in_executor(
                    None,
                    lambda: self._summarize_branch(node)
                )

            node.mark_complete()
            logger.info(f"[TreeExplorer] Async completed branch {node.id}: {len(node.findings)} findings")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[TreeExplorer] Failed to explore branch {node.id}: {e}")
            node.mark_failed(str(e))

    async def _explore_children_async(
        self,
        parent: ResearchTreeNode,
        state: Dict[str, Any],
        semaphore: Optional[asyncio.Semaphore] = None,
    ) -> None:
        """
        Async parallel exploration of child nodes with context isolation.

        Uses asyncio.gather() with semaphore to limit concurrency.
        Each child branch gets an isolated context to prevent cross-contamination.

        Args:
            parent: Parent node whose children to explore
            state: Agent state for cancellation
            semaphore: Optional semaphore for concurrency control
        """
        from agent.core.context import fork_state, merge_state

        if parent.depth >= self.max_depth:
            return

        # Get parallel branch limit from settings
        max_parallel = int(getattr(settings, "tree_parallel_branches", 3))
        if semaphore is None:
            semaphore = asyncio.Semaphore(max_parallel)

        # Decompose this node's topic
        subtopics = self.decompose_topic(
            parent.topic,
            existing_knowledge=parent.summary,
            num_subtopics=min(2, self.max_branches),
        )

        # Create child nodes
        children = []
        for subtopic, relevance in subtopics:
            child = self.tree.add_child(parent.id, subtopic, relevance)
            if child:
                children.append(child)

        if not children:
            return

        # Store child results for merging
        child_results = []
        results_lock = asyncio.Lock()

        async def explore_with_isolation(child: ResearchTreeNode) -> None:
            async with semaphore:
                self._check_cancel(state)

                # Fork state for this child branch
                scope_id = f"branch_{child.id}"
                forked_state = fork_state(state, scope_id, clear_messages=True)

                # Explore with isolated context
                await self.explore_branch_async(child, forked_state)

                # Collect results for later merge
                async with results_lock:
                    child_results.append((scope_id, forked_state))

        # Explore all children in parallel with isolated contexts
        logger.info(f"[TreeExplorer] Parallel exploring {len(children)} children of {parent.id} with context isolation")
        await asyncio.gather(*[explore_with_isolation(c) for c in children])

        # Merge all child results back to parent state
        for scope_id, child_state in child_results:
            updates = merge_state(state, child_state, scope_id)
            for key, value in updates.items():
                state[key] = value

        logger.info(f"[TreeExplorer] Merged {len(child_results)} child contexts")

    async def run_async(
        self,
        topic: str,
        state: Dict[str, Any],
        decompose_root: bool = True,
    ) -> ResearchTree:
        """
        Async version of run() with parallel branch exploration.

        Args:
            topic: The main topic to research
            state: Agent state for cancellation checking
            decompose_root: Whether to decompose root into subtopics

        Returns:
            The completed ResearchTree
        """
        self.start_time = time.time()
        self._check_cancel(state)

        # Initialize tree
        self.tree = ResearchTree(
            max_depth=self.max_depth,
            max_branches=self.max_branches,
        )

        # Create root
        root = self.tree.create_root(topic)

        # Explore root first (sync is fine for single node)
        logger.info(f"[TreeExplorer] Starting async tree exploration for: {topic}")
        self.explore_branch(root, state)

        # Decompose and explore sub-topics in parallel
        if decompose_root and self.max_depth > 0:
            self._check_cancel(state)

            # Decompose into subtopics
            subtopics = self.decompose_topic(
                topic,
                existing_knowledge=root.summary,
                num_subtopics=self.max_branches,
            )

            # Create child nodes
            children = []
            for subtopic, relevance in subtopics:
                child = self.tree.add_child(root.id, subtopic, relevance)
                if child:
                    children.append(child)

            if children:
                # Get parallel limit from settings
                max_parallel = int(getattr(settings, "tree_parallel_branches", 3))
                semaphore = asyncio.Semaphore(max_parallel)

                async def explore_child(child: ResearchTreeNode) -> None:
                    async with semaphore:
                        self._check_cancel(state)
                        await self.explore_branch_async(child, state)
                        # Recursively explore if depth allows
                        if child.depth < self.max_depth:
                            await self._explore_children_async(child, state, semaphore)

                # Explore all first-level children in parallel
                logger.info(f"[TreeExplorer] Parallel exploring {len(children)} subtopics")
                await asyncio.gather(*[explore_child(c) for c in children])

        elapsed = time.time() - self.start_time
        logger.info(
            f"[TreeExplorer] Async completed tree exploration in {elapsed:.2f}s\n"
            f"  Total nodes: {len(self.tree.nodes)}\n"
            f"  Completed: {len(self.tree.get_completed_nodes())}\n"
            f"  Total sources: {len(self.all_searched_urls)}"
        )

        return self.tree

    def _parse_list_output(self, text: str) -> List[str]:
        """Parse python-list-like output into a string list."""
        import ast

        if not text:
            return []

        fenced = re.findall(r"```(?:python)?(.*?)```", text, flags=re.S | re.I)
        if fenced:
            text = fenced[-1]

        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end > start:
            text = text[start:end + 1]

        try:
            data = ast.literal_eval(text)
            if isinstance(data, list):
                return [str(x).strip() for x in data if isinstance(x, (str, int, float))]
        except Exception:
            pass

        return [line.strip() for line in text.splitlines() if line.strip()]

    def get_final_summary(self) -> str:
        """Get the final merged summary from all branches."""
        if not self.tree:
            return ""

        completed = self.tree.get_completed_nodes()
        if not completed:
            return ""

        return self.merge_branches(completed)

    def get_all_sources(self) -> List[str]:
        """Get all unique sources found during exploration."""
        return self.all_searched_urls.copy()

    def get_all_findings(self) -> List[Dict[str, Any]]:
        """Get all findings from all nodes."""
        if not self.tree:
            return []
        return self.tree.get_all_findings()
