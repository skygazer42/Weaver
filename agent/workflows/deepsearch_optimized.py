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
import copy
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
from agent.core.search_cache import get_search_cache
from agent.workflows.domain_router import ResearchDomain, build_provider_profile

# Import knowledge gap analysis
from agent.workflows.knowledge_gap import KnowledgeGapAnalyzer
from agent.workflows.parsing_utils import format_search_results, parse_list_output
from agent.workflows.query_strategy import (
    analyze_query_coverage,
    backfill_diverse_queries,
    is_time_sensitive_topic,
    summarize_freshness,
)

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
from tools.search.multi_search import SearchStrategy, multi_search
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


def _resolve_search_strategy() -> SearchStrategy:
    raw = str(getattr(settings, "search_strategy", "fallback") or "fallback").strip().lower()
    try:
        return SearchStrategy(raw)
    except ValueError:
        logger.warning(f"[deepsearch] invalid search_strategy='{raw}', fallback to 'fallback'")
        return SearchStrategy.FALLBACK


def _normalize_multi_search_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        normalized.append(
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "summary": r.get("summary") or r.get("snippet", ""),
                "raw_excerpt": r.get("raw_excerpt") or r.get("content", ""),
                "score": float(r.get("score", 0.5) or 0.5),
                "published_date": r.get("published_date"),
                "provider": r.get("provider", ""),
            }
        )
    return normalized


def _resolve_provider_profile(state: Dict[str, Any]) -> Optional[List[str]]:
    """Build provider profile from domain routing metadata if present."""
    domain_config = state.get("domain_config") or {}
    suggested_sources = domain_config.get("suggested_sources", [])
    domain_value = (state.get("domain") or domain_config.get("domain") or "general")
    try:
        domain = ResearchDomain(str(domain_value).strip().lower())
    except ValueError:
        domain = ResearchDomain.GENERAL

    profile = build_provider_profile(suggested_sources=suggested_sources, domain=domain)
    return profile or None


def _cache_query_key(
    query: str,
    max_results: int,
    strategy: SearchStrategy,
    provider_profile: Optional[List[str]] = None,
) -> str:
    profile = ",".join((provider_profile or []))
    return f"deepsearch::{strategy.value}::{max_results}::{profile}::{query}"


def _estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    return max(1, len(str(text)) // 4)


def _estimate_tokens_from_results(results: List[Dict[str, Any]]) -> int:
    tokens = 0
    for result in results or []:
        if not isinstance(result, dict):
            continue
        tokens += _estimate_tokens_from_text(result.get("title", ""))
        snippet = (
            result.get("raw_excerpt")
            or result.get("summary")
            or result.get("snippet")
            or result.get("content")
            or ""
        )
        tokens += _estimate_tokens_from_text(str(snippet)[:600])
    return tokens


def _budget_stop_reason(
    start_ts: float,
    tokens_used: int,
    max_seconds: float,
    max_tokens: int,
) -> Optional[str]:
    if max_seconds > 0 and (time.time() - start_ts) >= max_seconds:
        return "time_budget_exceeded"
    if max_tokens > 0 and tokens_used >= max_tokens:
        return "token_budget_exceeded"
    return None


def _search_query(
    query: str,
    max_results: int,
    config: Dict[str, Any],
    provider_profile: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Search with multi-provider orchestration first, then Tavily fallback."""
    strategy = _resolve_search_strategy()
    cache = get_search_cache()
    cache_key = _cache_query_key(query, max_results, strategy, provider_profile)
    cached = cache.get(cache_key)
    if cached is not None:
        logger.info(f"[deepsearch] cache hit for query='{query[:80]}'")
        return copy.deepcopy(cached)

    try:
        kwargs: Dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "strategy": strategy,
        }
        if provider_profile:
            kwargs["provider_profile"] = provider_profile
        multi_results = multi_search(**kwargs)
        normalized = _normalize_multi_search_results(multi_results)
        if normalized:
            cache.set(cache_key, copy.deepcopy(normalized))
            return normalized
        logger.info(f"[deepsearch] multi_search returned no results for query='{query[:80]}'")
    except Exception as e:
        logger.warning(f"[deepsearch] multi_search failed, falling back to tavily: {e}")

    try:
        fallback_results = tavily_search.invoke(
            {"query": query, "max_results": max_results},
            config=config,
        )
        if fallback_results:
            cache.set(cache_key, copy.deepcopy(fallback_results))
        return fallback_results
    except Exception as e:
        logger.warning(f"[deepsearch] tavily fallback failed: {e}")
        return []


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
    return backfill_diverse_queries(
        topic=topic,
        existing_queries=clean,
        historical_queries=have_query,
        query_num=query_num,
    )


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




def _build_quality_diagnostics(topic: str, queries: List[str], search_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build query-coverage and freshness diagnostics for deepsearch runs."""
    query_coverage = analyze_query_coverage(queries)
    freshness_summary = summarize_freshness(search_runs)
    time_sensitive_query = is_time_sensitive_topic(topic)
    min_known_results = max(
        1, int(getattr(settings, "deepsearch_freshness_warning_min_known", 3) or 3)
    )
    min_fresh_ratio = max(
        0.0,
        min(1.0, float(getattr(settings, "deepsearch_freshness_warning_min_ratio", 0.4) or 0.4)),
    )

    freshness_warning = ""
    if (
        time_sensitive_query
        and freshness_summary.get("known_count", 0) >= min_known_results
        and freshness_summary.get("fresh_30_ratio", 0.0) < min_fresh_ratio
    ):
        freshness_warning = "low_freshness_for_time_sensitive_query"

    return {
        "query_coverage": query_coverage,
        "query_coverage_score": query_coverage.get("score", 0.0),
        "query_dimensions_covered": query_coverage.get("covered_dimensions", []),
        "query_dimensions_missing": query_coverage.get("missing_dimensions", []),
        "query_dimension_hits": query_coverage.get("dimension_hits", {}),
        "freshness_summary": freshness_summary,
        "time_sensitive_query": time_sensitive_query,
        "freshness_warning": freshness_warning,
    }


def _resolve_event_emitter(state: Dict[str, Any], config: Dict[str, Any]) -> Any:
    """Resolve thread-scoped emitter if available (best effort)."""
    cfg = config.get("configurable") if isinstance(config, dict) else {}
    thread_id = ""
    if isinstance(cfg, dict):
        thread_id = str(cfg.get("thread_id") or "").strip()
    if not thread_id:
        thread_id = str(state.get("cancel_token_id") or "").strip()
    if not thread_id:
        return None

    try:
        from agent.core.events import get_emitter_sync

        return get_emitter_sync(thread_id)
    except Exception:
        return None


def _emit_event(emitter: Any, event_type: str, data: Dict[str, Any]) -> None:
    """Emit an event from sync context without interrupting deepsearch flow."""
    if emitter is None:
        return
    try:
        emitter.emit_sync(event_type, data or {})
    except Exception as e:
        logger.debug(f"[deepsearch] failed to emit event '{event_type}': {e}")


def _compact_search_results(results: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    compact: List[Dict[str, Any]] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        compact.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "provider": item.get("provider", ""),
                "published_date": item.get("published_date"),
                "score": float(item.get("score", 0.0) or 0.0),
            }
        )
        if len(compact) >= max(1, int(limit)):
            break
    return compact


def _provider_breakdown(results: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in results or []:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "unknown").strip() or "unknown"
        counts[provider] = counts.get(provider, 0) + 1
    return counts


def _event_results_limit() -> int:
    return max(1, min(20, int(getattr(settings, "deepsearch_event_results_limit", 5) or 5)))


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
    max_seconds = max(0.0, float(getattr(settings, "deepsearch_max_seconds", 0.0)))
    max_tokens = max(0, int(getattr(settings, "deepsearch_max_tokens", 0)))

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
    provider_profile = _resolve_provider_profile(state)

    # URL deduplication mechanism - use set for O(1) lookup
    all_searched_urls: List[str] = []  # Ordered list for logging
    all_searched_urls_set: set = set()  # Fast lookup
    selected_urls: List[str] = []  # Already crawled URLs
    selected_urls_set: set = set()  # Fast lookup

    logger.info(f"[deepsearch] topic='{topic}' epochs={max_epochs}")
    logger.info(f"[deepsearch] 开始优化版深度搜索")

    start_ts = time.time()
    tokens_used = _estimate_tokens_from_text(topic)
    budget_stop_reason = ""
    emitter = _resolve_event_emitter(state, config)

    try:
        for epoch in range(max_epochs):
            try:
                _check_cancel(state)
                epoch_start = time.time()
                budget_stop_reason = _budget_stop_reason(
                    start_ts=start_ts,
                    tokens_used=tokens_used,
                    max_seconds=max_seconds,
                    max_tokens=max_tokens,
                )
                if budget_stop_reason:
                    logger.info(f"[deepsearch] 预算触发提前停止: {budget_stop_reason}")
                    break
                logger.info(f"[deepsearch] ===== Epoch {epoch + 1}/{max_epochs} =====")
                epoch_node_id = f"deepsearch_epoch_{epoch + 1}"
                _emit_event(
                    emitter,
                    "research_node_start",
                    {
                        "node_id": epoch_node_id,
                        "topic": topic,
                        "depth": 1,
                        "parent_id": "deepsearch",
                        "epoch": epoch + 1,
                    },
                )

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
                tokens_used += sum(_estimate_tokens_from_text(q) for q in queries)
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
                    budget_stop_reason = _budget_stop_reason(
                        start_ts=start_ts,
                        tokens_used=tokens_used,
                        max_seconds=max_seconds,
                        max_tokens=max_tokens,
                    )
                    if budget_stop_reason:
                        logger.info(f"[deepsearch] 搜索阶段触发预算停止: {budget_stop_reason}")
                        break

                    results = _search_query(
                        q,
                        per_query_results,
                        config,
                        provider_profile=provider_profile,
                    )
                    tokens_used += _estimate_tokens_from_results(results)
                    combined_results.extend(results)
                    search_runs.append(
                        {
                            "query": q,
                            "results": results,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                    provider_breakdown = _provider_breakdown(results)
                    provider_name = "unknown"
                    if len(provider_breakdown) > 1:
                        provider_name = "multi"
                    elif len(provider_breakdown) == 1:
                        provider_name = next(iter(provider_breakdown))
                    _emit_event(
                        emitter,
                        "search",
                        {
                            "query": q,
                            "provider": provider_name,
                            "provider_breakdown": provider_breakdown,
                            "results": _compact_search_results(results, limit=_event_results_limit()),
                            "count": len(results),
                            "epoch": epoch + 1,
                        },
                    )

                    # Record all searched URLs (dedupe with O(1) set lookup)
                    for r in results:
                        url = r.get("url")
                        if url and url not in all_searched_urls_set:
                            all_searched_urls.append(url)
                            all_searched_urls_set.add(url)

                if budget_stop_reason:
                    break

                logger.info(
                    f"[deepsearch] Epoch {epoch + 1}: 搜索到 {len(combined_results)} 个结果"
                    f" | 累计 URL: {len(all_searched_urls)}"
                    f" | 耗时 {time.time() - search_start:.2f}s"
                )

                if not combined_results:
                    logger.info(f"[deepsearch] Epoch {epoch + 1}: 无搜索结果，跳过本轮")
                    epoch_diagnostics = _build_quality_diagnostics(topic, have_query, search_runs)
                    _emit_event(
                        emitter,
                        "quality_update",
                        {
                            "epoch": epoch + 1,
                            "stage": "epoch",
                            **epoch_diagnostics,
                        },
                    )
                    _emit_event(
                        emitter,
                        "research_node_complete",
                        {
                            "node_id": epoch_node_id,
                            "summary": "",
                            "sources": [],
                            "quality": epoch_diagnostics,
                            "epoch": epoch + 1,
                        },
                    )
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
                    epoch_diagnostics = _build_quality_diagnostics(topic, have_query, search_runs)
                    _emit_event(
                        emitter,
                        "quality_update",
                        {
                            "epoch": epoch + 1,
                            "stage": "epoch",
                            **epoch_diagnostics,
                        },
                    )
                    _emit_event(
                        emitter,
                        "research_node_complete",
                        {
                            "node_id": epoch_node_id,
                            "summary": "",
                            "sources": [],
                            "quality": epoch_diagnostics,
                            "epoch": epoch + 1,
                        },
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
                    tokens_used += _estimate_tokens_from_text(summary_text)

                logger.info(
                    f"[deepsearch] Epoch {epoch + 1}: 摘要完成"
                    f" | 足够: {enough}"
                    f" | 摘要长度: {len(summary_text)}"
                    f" | 耗时 {time.time() - summary_start:.2f}s"
                )
                budget_stop_reason = _budget_stop_reason(
                    start_ts=start_ts,
                    tokens_used=tokens_used,
                    max_seconds=max_seconds,
                    max_tokens=max_tokens,
                )
                if budget_stop_reason:
                    logger.info(f"[deepsearch] 摘要后触发预算停止: {budget_stop_reason}")
                    break

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
                epoch_diagnostics = _build_quality_diagnostics(topic, have_query, search_runs)
                _emit_event(
                    emitter,
                    "quality_update",
                    {
                        "epoch": epoch + 1,
                        "stage": "epoch",
                        **epoch_diagnostics,
                    },
                )
                _emit_event(
                    emitter,
                    "research_node_complete",
                    {
                        "node_id": epoch_node_id,
                        "summary": summary_text[:1200] if isinstance(summary_text, str) else "",
                        "sources": _compact_search_results(
                            chosen_results,
                            limit=_event_results_limit(),
                        ),
                        "quality": epoch_diagnostics,
                        "epoch": epoch + 1,
                    },
                )

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
            f"\n  估算Token: {tokens_used}"
            f"\n  预算停止原因: {budget_stop_reason or 'none'}"
        )

        diagnostics = _build_quality_diagnostics(topic, have_query, search_runs)
        quality_summary = {
            "epochs_completed": epoch + 1,
            "summary_count": len(summary_notes),
            "source_count": len(all_searched_urls),
            "selected_url_count": len(selected_urls),
            "budget_stop_reason": budget_stop_reason or "",
            "tokens_used": tokens_used,
            "elapsed_seconds": elapsed,
            **diagnostics,
        }
        deepsearch_artifacts = {
            "mode": "linear",
            "queries": have_query,
            "research_tree": None,
            "quality_summary": quality_summary,
            "query_coverage": diagnostics.get("query_coverage", {}),
            "freshness_summary": diagnostics.get("freshness_summary", {}),
        }

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
        if budget_stop_reason:
            messages.append(
                AIMessage(
                    content=(
                        "（由于预算限制提前收敛："
                        f"{budget_stop_reason}; tokens={tokens_used}; elapsed={elapsed:.2f}s）"
                    )
                )
            )
        if diagnostics.get("freshness_warning"):
            messages.append(
                AIMessage(
                    content="（时间敏感问题的新鲜来源占比较低，建议补充近30天来源并重试。）"
                )
            )

        return {
            "research_plan": have_query,
            "scraped_content": search_runs,
            "draft_report": final_report,
            "final_report": final_report,
            "quality_summary": quality_summary,
            "deepsearch_artifacts": deepsearch_artifacts,
            "deepsearch_mode": "linear",
            "messages": messages,
            "is_complete": False,
            "budget_stop_reason": budget_stop_reason,
            "deepsearch_tokens_used": tokens_used,
            "deepsearch_elapsed_seconds": elapsed,
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
    max_seconds = max(0.0, float(getattr(settings, "deepsearch_max_seconds", 0.0)))
    max_tokens = max(0, int(getattr(settings, "deepsearch_max_tokens", 0)))

    logger.info(
        f"[deepsearch-tree] Starting tree exploration: topic='{topic}' "
        f"depth={max_depth} branches={max_branches} parallel={parallel_branches}"
    )
    provider_profile = _resolve_provider_profile(state)
    emitter = _resolve_event_emitter(state, config)
    _emit_event(
        emitter,
        "research_node_start",
        {
            "node_id": "deepsearch_tree",
            "topic": topic,
            "depth": 0,
            "parent_id": "deepsearch",
        },
    )

    start_ts = time.time()
    budget_stop_reason = ""
    tokens_used = _estimate_tokens_from_text(topic)

    budget_stop_reason = _budget_stop_reason(
        start_ts=start_ts,
        tokens_used=tokens_used,
        max_seconds=max_seconds,
        max_tokens=max_tokens,
    )
    if budget_stop_reason:
        diagnostics = _build_quality_diagnostics(topic, [], [])
        quality_summary = {
            "epochs_completed": 0,
            "summary_count": 0,
            "source_count": 0,
            "budget_stop_reason": budget_stop_reason,
            "tokens_used": tokens_used,
            "elapsed_seconds": 0.0,
            **diagnostics,
        }
        _emit_event(emitter, "quality_update", {"epoch": 0, "stage": "budget_stop", **diagnostics})
        _emit_event(
            emitter,
            "research_node_complete",
            {
                "node_id": "deepsearch_tree",
                "summary": "",
                "sources": [],
                "quality": diagnostics,
                "epoch": 0,
            },
        )
        return {
            "research_plan": [],
            "scraped_content": [],
            "draft_report": summary_text_prompt,
            "final_report": summary_text_prompt,
            "messages": [
                AIMessage(content=f"（预算限制触发，未执行树搜索：{budget_stop_reason}）")
            ],
            "is_complete": False,
            "budget_stop_reason": budget_stop_reason,
            "deepsearch_tokens_used": tokens_used,
            "deepsearch_elapsed_seconds": 0.0,
            "quality_summary": quality_summary,
            "deepsearch_artifacts": {
                "mode": "tree",
                "queries": [],
                "research_tree": None,
                "quality_summary": quality_summary,
                "query_coverage": diagnostics.get("query_coverage", {}),
                "freshness_summary": diagnostics.get("freshness_summary", {}),
            },
            "deepsearch_mode": "tree",
        }

    try:
        # Create tree explorer
        explorer = TreeExplorer(
            planner_llm=planner_llm,
            researcher_llm=critic_llm,
            writer_llm=writer_llm,
            search_func=lambda payload, config_payload=None: _search_query(
                (payload or {}).get("query", ""),
                int((payload or {}).get("max_results", per_query_results)),
                config_payload if isinstance(config_payload, dict) else config,
                provider_profile=provider_profile,
            ),
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
        tokens_used += _estimate_tokens_from_text(merged_summary)
        tokens_used += _estimate_tokens_from_text(final_report)
        post_budget_reason = _budget_stop_reason(
            start_ts=start_ts,
            tokens_used=tokens_used,
            max_seconds=max_seconds,
            max_tokens=max_tokens,
        )
        if post_budget_reason:
            budget_stop_reason = post_budget_reason

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
        diagnostics = _build_quality_diagnostics(topic, have_query, search_runs)
        for run in search_runs:
            results = run.get("results") if isinstance(run, dict) else []
            provider_breakdown = _provider_breakdown(results if isinstance(results, list) else [])
            provider_name = "unknown"
            if len(provider_breakdown) > 1:
                provider_name = "multi"
            elif len(provider_breakdown) == 1:
                provider_name = next(iter(provider_breakdown))
            _emit_event(
                emitter,
                "search",
                {
                    "query": run.get("query", "") if isinstance(run, dict) else "",
                    "provider": provider_name,
                    "provider_breakdown": provider_breakdown,
                    "results": _compact_search_results(
                        results if isinstance(results, list) else [],
                        limit=_event_results_limit(),
                    ),
                    "count": len(results) if isinstance(results, list) else 0,
                    "mode": "tree",
                    "epoch": 1,
                },
            )

        quality_summary = {
            "epochs_completed": 1,
            "summary_count": len(summary_notes),
            "source_count": len(all_sources),
            "tree_node_count": len(tree.nodes),
            "budget_stop_reason": budget_stop_reason or "",
            "tokens_used": tokens_used,
            "elapsed_seconds": elapsed,
            **diagnostics,
        }
        deepsearch_artifacts = {
            "mode": "tree",
            "queries": have_query,
            "research_tree": tree.to_dict(),
            "quality_summary": quality_summary,
            "query_coverage": diagnostics.get("query_coverage", {}),
            "freshness_summary": diagnostics.get("freshness_summary", {}),
        }
        _emit_event(emitter, "quality_update", {"epoch": 1, "stage": "final", **diagnostics})
        _emit_event(
            emitter,
            "research_tree_update",
            {
                "tree": tree.to_dict(),
                "quality": diagnostics,
            },
        )
        _emit_event(
            emitter,
            "research_node_complete",
            {
                "node_id": "deepsearch_tree",
                "summary": final_report[:1200] if isinstance(final_report, str) else "",
                "sources": _compact_search_results(
                    [r.get("result", {}) for r in all_findings],
                    limit=_event_results_limit(),
                ),
                "quality": diagnostics,
            },
        )

        messages = [AIMessage(content=final_report)]
        if save_path:
            messages.append(AIMessage(content=f"(数据已保存: {save_path})"))
        if budget_stop_reason:
            messages.append(AIMessage(content=f"（预算限制提示：{budget_stop_reason}）"))
        if diagnostics.get("freshness_warning"):
            messages.append(
                AIMessage(content="（时间敏感问题的新鲜来源占比较低，建议补充近30天来源并重试。）")
            )

        return {
            "research_plan": have_query,
            "scraped_content": search_runs,
            "draft_report": final_report,
            "final_report": final_report,
            "quality_summary": quality_summary,
            "deepsearch_artifacts": deepsearch_artifacts,
            "deepsearch_mode": "tree",
            "messages": messages,
            "research_tree": tree.to_dict(),
            "is_complete": False,
            "budget_stop_reason": budget_stop_reason,
            "deepsearch_tokens_used": tokens_used,
            "deepsearch_elapsed_seconds": elapsed,
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
