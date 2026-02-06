"""
Optimized DeepSearch implementation with enhanced features.

Key improvements:
1. URL deduplication mechanism
2. Detailed performance logging
3. Enhanced error handling
4. Better cancellation support
5. OOP encapsulation (optional)
6. Tree-based exploration (new)
7. Multi-model support (new)

Based on: deep_search-dev reference implementation
"""

import asyncio
import json
import logging
import re
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from agent.core.llm_factory import create_chat_model

# Import knowledge gap analysis
from agent.workflows.knowledge_gap import KnowledgeGapAnalyzer
from agent.workflows.parsing_utils import format_search_results, parse_list_output

# Import tree-based research components
from agent.workflows.research_tree import ResearchTree, TreeExplorer
from common.cancellation import check_cancellation as _check_cancel_token
from common.config import settings
from prompts.templates.deepsearch import (
    final_summary_prompt,
    formulate_query_prompt,
    related_url_prompt,
    summary_crawl_prompt,
    summary_text_prompt,
)
from tools.crawl.crawler import crawl_urls
from tools.search.search import tavily_search

logger = logging.getLogger(__name__)

# Use shared implementations
_chat_model = create_chat_model
_parse_list_output = parse_list_output
_format_results = format_search_results

_DEEPSEARCH_MODES = {"auto", "tree", "linear"}


def _check_cancel(state: Dict[str, Any]) -> None:
    """Respect cancellation flags/tokens."""
    if state.get("is_cancelled"):
        raise asyncio.CancelledError("Task was cancelled (flag)")
    token_id = state.get("cancel_token_id")
    if token_id:
        _check_cancel_token(token_id)


def _normalize_deepsearch_mode(value: Any) -> str:
    """Normalize deepsearch mode to one of: auto, tree, linear."""
    mode = str(value or "").strip().lower()
    if mode in _DEEPSEARCH_MODES:
        return mode
    return "auto"


def _resolve_deepsearch_mode(config: Dict[str, Any]) -> str:
    """
    Resolve deepsearch mode with precedence:
    1. request/configurable.deepsearch_mode
    2. settings.deepsearch_mode
    3. auto
    """
    cfg = config.get("configurable") or {}
    runtime_mode = cfg.get("deepsearch_mode") if isinstance(cfg, dict) else None
    if runtime_mode is not None:
        return _normalize_deepsearch_mode(runtime_mode)

    return _normalize_deepsearch_mode(getattr(settings, "deepsearch_mode", "auto"))


def _selected_model(config: Dict[str, Any], fallback: str) -> str:
    cfg = config.get("configurable") or {}
    if isinstance(cfg, dict):
        val = cfg.get("model")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback


def _selected_reasoning_model(config: Dict[str, Any], fallback: str) -> str:
    cfg = config.get("configurable") or {}
    if isinstance(cfg, dict):
        val = cfg.get("reasoning_model")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback


def _model_for_task(task_type: str, config: Dict[str, Any]) -> str:
    """
    Get model name for a specific task type using the ModelRouter.

    Args:
        task_type: One of: planning, query_gen, research, critique, synthesis, writing
        config: RunnableConfig dict with optional overrides
    """
    try:
        from agent.core.multi_model import TaskType, get_model_router

        tt = TaskType(task_type)
        router = get_model_router()
        return router.get_model_name(tt, config)
    except Exception:
        # Fallback to legacy behavior
        if task_type in ("planning", "query_gen", "critique", "gap_analysis"):
            return _selected_reasoning_model(config, settings.reasoning_model)
        return _selected_model(config, settings.primary_model)


def _generate_queries(
    llm: ChatOpenAI,
    topic: str,
    have_query: List[str],
    summary_notes: List[str],
    query_num: int,
    config: Dict[str, Any],
    missing_topics: Optional[List[str]] = None,
) -> List[str]:
    """Generate new search queries based on topic, existing knowledge, and knowledge gaps.

    If missing_topics is provided (from gap analysis), prioritizes those areas.
    """
    # If we have missing topics from gap analysis, incorporate them
    enhanced_topic = topic
    if missing_topics:
        gap_hint = f"\n\n注意：以下方面信息仍然不足，请优先覆盖：{', '.join(missing_topics[:3])}"
        enhanced_topic = topic + gap_hint

    prompt = ChatPromptTemplate.from_messages([("user", formulate_query_prompt)])
    msg = prompt.format_messages(
        topic=enhanced_topic,
        have_query=", ".join(have_query) or "[]",
        summary_search="\n\n".join(summary_notes) or "暂无",
        query_num=query_num,
    )
    response = llm.invoke(msg, config=config)
    content = getattr(response, "content", "") or ""
    queries = _parse_list_output(content)
    # Deduplicate and trim
    seen = set(q.lower() for q in have_query)
    clean: List[str] = []
    for q in queries:
        if not q:
            continue
        q_norm = q.strip()
        if not q_norm or q_norm.lower() in seen:
            continue
        seen.add(q_norm.lower())
        clean.append(q_norm)
        if len(clean) >= query_num:
            break
    return clean


def _pick_relevant_urls(
    llm: ChatOpenAI,
    topic: str,
    summary_notes: List[str],
    results: List[Dict[str, Any]],
    max_urls: int,
    config: Dict[str, Any],
    selected_urls_set: set,  # Use set for O(1) lookup
) -> List[str]:
    """Pick relevant URLs from search results, excluding already selected ones."""
    if not results:
        return []

    # Filter already selected URLs with O(1) set lookup
    available_results = [r for r in results if r.get("url") and r.get("url") not in selected_urls_set]

    if not available_results:
        logger.info("All URLs have been selected, no new URLs available")
        return []

    formatted = _format_results(available_results)
    prompt = ChatPromptTemplate.from_messages([("user", related_url_prompt)])
    msg = prompt.format_messages(
        topic=topic,
        summary_search="\n\n".join(summary_notes) or "暂无",
        text=formatted,
    )
    response = llm.invoke(msg, config=config)
    urls = _parse_list_output(getattr(response, "content", "") or "")

    # Fallback: top scores
    if not urls:
        sorted_results = sorted(available_results, key=lambda r: r.get("score", 0), reverse=True)
        urls = [r.get("url") for r in sorted_results if r.get("url")]

    # Clamp and dedupe
    deduped: List[str] = []
    seen = set()
    for u in urls:
        if not isinstance(u, str):
            continue
        u = u.strip()
        if not u or u in seen or u in selected_urls_set:
            continue
        seen.add(u)
        deduped.append(u)
        if len(deduped) >= max_urls:
            break
    return deduped


def _summarize_new_knowledge(
    llm: ChatOpenAI,
    topic: str,
    summary_notes: List[str],
    chosen_results: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> Tuple[bool, str]:
    """Summarize new knowledge and judge if information is sufficient."""
    if not chosen_results:
        return False, ""

    prompt = ChatPromptTemplate.from_messages([("user", summary_crawl_prompt)])
    msg = prompt.format_messages(
        summary_search="\n\n".join(summary_notes) or "暂无",
        crawl_res=_format_results(chosen_results),
        topic=topic,
    )
    response = llm.invoke(msg, config=config)
    content = getattr(response, "content", "") or ""
    lowered = content.lower()
    enough = "回答" in lowered and "yes" in lowered.split("回答", 1)[-1]

    # Extract summary after "总结:" if present
    summary_text = ""
    if "总结" in content:
        summary_text = content.split("总结", 1)[-1].strip(":： \n")
    if not summary_text:
        summary_text = content
    return enough, summary_text.strip()


def _final_report(
    llm: ChatOpenAI, topic: str, summary_notes: List[str], config: Dict[str, Any]
) -> str:
    """Generate final report based on all summaries."""
    prompt = ChatPromptTemplate.from_messages([("user", final_summary_prompt)])
    msg = prompt.format_messages(
        topic=topic,
        summary_search="\n\n".join(summary_notes) or "暂无",
    )
    response = llm.invoke(msg, config=config)
    return getattr(response, "content", "") or summary_text_prompt


def _hydrate_with_crawler(results: List[Dict[str, Any]]) -> None:
    """Enrich results in-place with crawled content when Tavily lacks body text."""
    if not settings.deepsearch_enable_crawler or not results:
        return

    # Pick URLs that need content
    targets = []
    for r in results:
        body = r.get("raw_excerpt") or r.get("summary") or ""
        if len(body) < 200 and r.get("url"):
            targets.append(r["url"])
    if not targets:
        return

    crawled = {item["url"]: item for item in crawl_urls(targets)}
    for r in results:
        url = r.get("url")
        if not url or url not in crawled:
            continue
        content = crawled[url].get("content") or ""
        if content:
            r["raw_excerpt"] = content[:1200]
            if not r.get("summary"):
                r["summary"] = content[:400]


def _safe_filename(name: str) -> str:
    return re.sub(r'[\/\\:\*\?"<>\|]', "_", name)[:80]


def _save_deepsearch_data(
    topic: str,
    have_query: List[str],
    summary_notes: List[str],
    search_runs: List[Dict[str, Any]],
    final_report: str,
    epoch: int,
) -> str:
    """Persist deepsearch run data if enabled."""
    if not settings.deepsearch_save_data:
        return ""

    try:
        save_dir = Path(settings.deepsearch_save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{_safe_filename(topic)}_{ts}.json"
        path = save_dir / fname
        data = {
            "topic": topic,
            "queries": have_query,
            "summaries": summary_notes,
            "search_runs": search_runs,
            "final_report": final_report,
            "epoch": epoch,
            "mode": "deepsearch_optimized",
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"[deepsearch] saved run data -> {path}")
        return str(path)
    except Exception as e:
        logger.warning(f"[deepsearch] failed to save data: {e}")
        return ""


def run_deepsearch_optimized(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optimized iterative deep-search pipeline.

    Improvements:
    1. URL deduplication to avoid repeated crawling
    2. Detailed performance logging for each step
    3. Enhanced error handling (single epoch failure doesn't break flow)
    4. Better cancellation support
    5. Maintains all_searched_urls and selected_urls
    """
    topic = state.get("input", "")
    _check_cancel(state)

    max_epochs = int(getattr(settings, "deepsearch_max_epochs", 3))
    query_num = int(getattr(settings, "deepsearch_query_num", 5))
    per_query_results = int(getattr(settings, "deepsearch_results_per_query", 5))
    top_urls = max(3, min(5, per_query_results))

    # Use multi-model routing for different task types
    planning_model = _model_for_task("planning", config)
    research_model = _model_for_task("research", config)
    writing_model = _model_for_task("writing", config)

    planner_llm = _chat_model(planning_model, temperature=0.8)
    critic_llm = _chat_model(research_model, temperature=0.2)
    writer_llm = _chat_model(writing_model, temperature=0.5)

    have_query: List[str] = []
    summary_notes: List[str] = []
    search_runs: List[Dict[str, Any]] = []

    # URL deduplication mechanism - use set for O(1) lookup
    all_searched_urls: List[str] = []  # Ordered list for logging
    all_searched_urls_set: set = set()  # Fast lookup
    selected_urls: List[str] = []  # Already crawled URLs
    selected_urls_set: set = set()  # Fast lookup

    logger.info(f"[deepsearch] topic='{topic}' epochs={max_epochs}")
    logger.info(f"[deepsearch] 开始优化版深度搜索")

    start_ts = time.time()

    try:
        for epoch in range(max_epochs):
            try:
                _check_cancel(state)
                epoch_start = time.time()
                logger.info(f"[deepsearch] ===== Epoch {epoch + 1}/{max_epochs} =====")

                # ⏱️ Step 1: 生成查询 (利用知识空白分析结果)
                query_start = time.time()
                missing_topics = state.get("missing_topics", []) if epoch > 0 else []
                queries = _generate_queries(
                    planner_llm, topic, have_query, summary_notes, query_num, config,
                    missing_topics=missing_topics,
                )
                if epoch == 0 and topic not in queries:
                    queries.append(topic)
                if not queries:
                    queries = [topic]
                have_query.extend(q for q in queries if q not in have_query)
                logger.info(
                    f"[deepsearch] Epoch {epoch + 1}: 生成 {len(queries)} 个查询"
                    f" | 耗时 {time.time() - query_start:.2f}s"
                )
                logger.debug(f"[deepsearch] 查询列表: {queries}")

                # ⏱️ Step 2: 并行搜索
                search_start = time.time()
                combined_results: List[Dict[str, Any]] = []
                for q in queries:
                    _check_cancel(state)
                    results = tavily_search.invoke(
                        {"query": q, "max_results": per_query_results},
                        config=config,
                    )
                    combined_results.extend(results)
                    search_runs.append(
                        {
                            "query": q,
                            "results": results,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                    # Record all searched URLs (dedupe with O(1) set lookup)
                    for r in results:
                        url = r.get("url")
                        if url and url not in all_searched_urls_set:
                            all_searched_urls.append(url)
                            all_searched_urls_set.add(url)

                logger.info(
                    f"[deepsearch] Epoch {epoch + 1}: 搜索到 {len(combined_results)} 个结果"
                    f" | 累计 URL: {len(all_searched_urls)}"
                    f" | 耗时 {time.time() - search_start:.2f}s"
                )

                if not combined_results:
                    logger.info(f"[deepsearch] Epoch {epoch + 1}: 无搜索结果，跳过本轮")
                    continue

                # Step 3: Pick most relevant URLs (excluding already selected)
                pick_start = time.time()
                chosen_urls = _pick_relevant_urls(
                    critic_llm,
                    topic,
                    summary_notes,
                    combined_results,
                    top_urls,
                    config,
                    selected_urls_set,  # Pass set for O(1) lookup
                )

                if not chosen_urls:
                    logger.warning(
                        f"[deepsearch] Epoch {epoch + 1}: No new URLs available, skipping"
                    )
                    continue

                # Update selected URLs list and set
                selected_urls.extend(chosen_urls)
                selected_urls_set.update(chosen_urls)

                chosen_urls_set = set(chosen_urls)
                chosen_results = [r for r in combined_results if r.get("url") in chosen_urls_set]
                if not chosen_results:
                    chosen_results = sorted(
                        combined_results, key=lambda r: r.get("score", 0), reverse=True
                    )[:top_urls]

                logger.info(
                    f"[deepsearch] Epoch {epoch + 1}: 选择 {len(chosen_urls)} 个 URL"
                    f" | 已选总数: {len(selected_urls)}"
                    f" | 耗时 {time.time() - pick_start:.2f}s"
                )

                # ⏱️ Step 4: 爬虫补充内容（可选）
                if settings.deepsearch_enable_crawler:
                    crawl_start = time.time()
                    _hydrate_with_crawler(chosen_results)
                    logger.info(
                        f"[deepsearch] Epoch {epoch + 1}: 爬虫增强完成"
                        f" | 耗时 {time.time() - crawl_start:.2f}s"
                    )

                # ⏱️ Step 5: 摘要新知识 + 判断是否足够
                summary_start = time.time()
                enough, summary_text = _summarize_new_knowledge(
                    critic_llm, topic, summary_notes, chosen_results, config
                )
                if summary_text:
                    summary_notes.append(summary_text)

                logger.info(
                    f"[deepsearch] Epoch {epoch + 1}: 摘要完成"
                    f" | 足够: {enough}"
                    f" | 摘要长度: {len(summary_text)}"
                    f" | 耗时 {time.time() - summary_start:.2f}s"
                )

                # ⏱️ Step 5.5: 知识空白分析 (可选)
                use_gap_analysis = getattr(settings, "deepsearch_use_gap_analysis", True)
                if use_gap_analysis and not enough and epoch < max_epochs - 1:
                    gap_start = time.time()
                    try:
                        gap_model = _model_for_task("gap_analysis", config)
                        gap_llm = _chat_model(gap_model, temperature=0.3)
                        gap_analyzer = KnowledgeGapAnalyzer(gap_llm, config, coverage_threshold=0.8)

                        # Analyze current knowledge state
                        collected_knowledge = "\n\n".join(summary_notes)
                        gap_result = gap_analyzer.analyze(topic, have_query, collected_knowledge)

                        logger.info(
                            f"[deepsearch] Epoch {epoch + 1}: 知识空白分析完成"
                            f" | 覆盖率: {gap_result.overall_coverage:.2f}"
                            f" | 空白数: {len(gap_result.gaps)}"
                            f" | 耗时 {time.time() - gap_start:.2f}s"
                        )

                        # Use gap analysis to determine if we can stop early
                        if gap_analyzer.is_research_sufficient(gap_result):
                            logger.info(f"[deepsearch] Epoch {epoch + 1}: 知识空白分析判定信息足够")
                            enough = True

                        # Get high-priority aspects for next round's query generation
                        high_priority_aspects = gap_analyzer.get_high_priority_aspects(gap_result)
                        if high_priority_aspects:
                            logger.info(
                                f"[deepsearch] 高优先级空白: {', '.join(high_priority_aspects[:3])}"
                            )
                            # Store for use in next epoch's query generation
                            state["missing_topics"] = high_priority_aspects

                    except Exception as e:
                        logger.warning(f"[deepsearch] 知识空白分析失败，继续常规流程: {e}")

                epoch_duration = time.time() - epoch_start
                logger.info(f"[deepsearch] Epoch {epoch + 1}: 总耗时 {epoch_duration:.2f}s")

                # 如果信息足够，提前结束
                if enough:
                    logger.info(f"[deepsearch] Epoch {epoch + 1}: 信息已足够，提前结束")
                    break

            except asyncio.CancelledError:
                raise  # 继续向上抛出
            except Exception as e:
                logger.error(f"[deepsearch] Epoch {epoch + 1} 失败: {str(e)}", exc_info=True)
                logger.error(traceback.format_exc())
                logger.info(f"[deepsearch] 继续下一轮搜索...")
                continue  # 单轮失败不影响整体流程

        # ⏱️ Step 6: 生成最终报告
        report_start = time.time()
        final_report = (
            _final_report(writer_llm, topic, summary_notes, config)
            if summary_notes
            else summary_text_prompt
        )
        logger.info(
            f"[deepsearch] 最终报告生成完成"
            f" | 字数: {len(final_report)}"
            f" | 耗时 {time.time() - report_start:.2f}s"
        )

        elapsed = time.time() - start_ts
        logger.info(
            f"[deepsearch] ===== 完成 ====="
            f"\n  总耗时: {elapsed:.2f}s"
            f"\n  总轮次: {epoch + 1}"
            f"\n  总查询: {len(have_query)}"
            f"\n  总 URL: {len(all_searched_urls)}"
            f"\n  已爬取: {len(selected_urls)}"
            f"\n  摘要数: {len(summary_notes)}"
        )

        # 保存数据
        save_path = _save_deepsearch_data(
            topic,
            have_query,
            summary_notes,
            search_runs,
            final_report,
            epoch=epoch + 1,
        )

        messages = [AIMessage(content=final_report)]
        if save_path:
            messages.append(AIMessage(content=f"(数据已保存: {save_path})"))

        return {
            "research_plan": have_query,
            "scraped_content": search_runs,
            "draft_report": final_report,
            "final_report": final_report,
            "messages": messages,
            "is_complete": False,
        }

    except asyncio.CancelledError:
        logger.warning("[deepsearch] 收到取消信号，停止任务")
        return {
            "is_cancelled": True,
            "is_complete": True,
            "errors": ["DeepSearch was cancelled"],
            "final_report": "任务已被取消",
        }


def run_deepsearch_tree(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tree-based deep search pipeline.

    Uses hierarchical topic decomposition and parallel branch exploration
    for more comprehensive research coverage.

    Inspired by GPT Researcher's tree exploration approach.
    """
    topic = state.get("input", "")
    _check_cancel(state)

    # Use multi-model routing for different task types
    planning_model = _model_for_task("planning", config)
    research_model = _model_for_task("research", config)
    writing_model = _model_for_task("writing", config)

    planner_llm = _chat_model(planning_model, temperature=0.8)
    critic_llm = _chat_model(research_model, temperature=0.2)
    writer_llm = _chat_model(writing_model, temperature=0.5)

    max_depth = int(getattr(settings, "tree_max_depth", 2))
    max_branches = int(getattr(settings, "tree_max_branches", 4))
    queries_per_branch = int(getattr(settings, "tree_queries_per_branch", 3))
    per_query_results = int(getattr(settings, "deepsearch_results_per_query", 5))
    parallel_branches = int(getattr(settings, "tree_parallel_branches", 3))

    logger.info(
        f"[deepsearch-tree] Starting tree exploration: topic='{topic}' "
        f"depth={max_depth} branches={max_branches} parallel={parallel_branches}"
    )

    start_ts = time.time()

    try:
        # Create tree explorer
        explorer = TreeExplorer(
            planner_llm=planner_llm,
            researcher_llm=critic_llm,
            writer_llm=writer_llm,
            search_func=tavily_search.invoke,
            config=config,
            max_depth=max_depth,
            max_branches=max_branches,
            queries_per_branch=queries_per_branch,
        )

        # Run tree exploration (use async if parallel_branches > 0)
        if parallel_branches > 0:
            # Use async parallel exploration
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If already in async context, use run_in_executor
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            lambda: asyncio.run(explorer.run_async(topic, state, decompose_root=True))
                        )
                        tree = future.result()
                else:
                    tree = loop.run_until_complete(explorer.run_async(topic, state, decompose_root=True))
            except RuntimeError:
                # No event loop, create one
                tree = asyncio.run(explorer.run_async(topic, state, decompose_root=True))
            logger.info(f"[deepsearch-tree] Used async parallel exploration")
        else:
            tree = explorer.run(topic, state, decompose_root=True)

        # Get merged summary from all branches
        merged_summary = explorer.get_final_summary()
        all_sources = explorer.get_all_sources()
        all_findings = explorer.get_all_findings()

        # Generate final report using the comprehensive summary
        summary_notes = [merged_summary] if merged_summary else []
        final_report = (
            _final_report(writer_llm, topic, summary_notes, config)
            if summary_notes
            else summary_text_prompt
        )

        elapsed = time.time() - start_ts
        logger.info(
            f"[deepsearch-tree] ===== Completed =====\n"
            f"  Total time: {elapsed:.2f}s\n"
            f"  Tree nodes: {len(tree.nodes)}\n"
            f"  Total sources: {len(all_sources)}\n"
            f"  Report length: {len(final_report)} chars"
        )

        # Collect queries from all nodes
        have_query = []
        search_runs = []
        for node in tree.nodes.values():
            have_query.extend(node.queries)
            for finding in node.findings:
                search_runs.append({
                    "query": finding.get("query", ""),
                    "results": [finding.get("result", {})],
                    "timestamp": finding.get("timestamp", ""),
                    "branch_id": node.id,
                    "branch_topic": node.topic,
                })

        # Save data
        save_path = _save_deepsearch_data(
            topic, have_query, summary_notes, search_runs, final_report, epoch=1,
        )

        messages = [AIMessage(content=final_report)]
        if save_path:
            messages.append(AIMessage(content=f"(数据已保存: {save_path})"))

        return {
            "research_plan": have_query,
            "scraped_content": search_runs,
            "draft_report": final_report,
            "final_report": final_report,
            "messages": messages,
            "research_tree": tree.to_dict(),
            "is_complete": False,
        }

    except asyncio.CancelledError:
        logger.warning("[deepsearch-tree] 收到取消信号，停止任务")
        return {
            "is_cancelled": True,
            "is_complete": True,
            "errors": ["DeepSearch was cancelled"],
            "final_report": "任务已被取消",
        }
    except Exception as e:
        logger.error(f"[deepsearch-tree] Failed: {e}", exc_info=True)
        # Fallback to linear mode
        logger.info("[deepsearch-tree] Falling back to linear deepsearch...")
        return run_deepsearch_optimized(state, config)


def run_deepsearch_auto(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Auto-select between tree and linear deep search based on settings.

    Uses tree-based exploration if enabled in settings, otherwise falls back
    to the optimized linear approach.
    """
    mode = _resolve_deepsearch_mode(config)

    if mode == "tree":
        logger.info("[deepsearch] Using tree-based exploration mode (override)")
        return run_deepsearch_tree(state, config)

    if mode == "linear":
        logger.info("[deepsearch] Using linear exploration mode (override)")
        return run_deepsearch_optimized(state, config)

    use_tree = getattr(settings, "tree_exploration_enabled", True)
    if use_tree:
        logger.info("[deepsearch] Using tree-based exploration mode")
        return run_deepsearch_tree(state, config)

    logger.info("[deepsearch] Using linear exploration mode")
    return run_deepsearch_optimized(state, config)
