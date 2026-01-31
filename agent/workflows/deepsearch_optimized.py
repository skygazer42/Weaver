"""
Optimized DeepSearch implementation with enhanced features.

Key improvements:
1. URL deduplication mechanism
2. Detailed performance logging
3. Enhanced error handling
4. Better cancellation support
5. OOP encapsulation (optional)

Based on: deep_search-dev reference implementation
"""

import ast
import asyncio
import json
import logging
import re
import textwrap
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

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


def _chat_model(model: str, temperature: float) -> ChatOpenAI:
    """Build a ChatOpenAI client that honors OpenAI/Azure/base_url overrides."""
    params: Dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "api_key": settings.openai_api_key,
        "timeout": settings.openai_timeout or None,
    }

    if settings.use_azure:
        params.update(
            {
                "azure_endpoint": settings.azure_endpoint or None,
                "azure_deployment": model,
                "api_version": settings.azure_api_version or None,
                "api_key": settings.azure_api_key or settings.openai_api_key,
            }
        )
    elif settings.openai_base_url:
        params["base_url"] = settings.openai_base_url

    if settings.openai_extra_body:
        try:
            params["extra_body"] = json.loads(settings.openai_extra_body)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in openai_extra_body; ignoring.")

    return ChatOpenAI(**params)


def _check_cancel(state: Dict[str, Any]) -> None:
    """Respect cancellation flags/tokens."""
    if state.get("is_cancelled"):
        raise asyncio.CancelledError("Task was cancelled (flag)")
    token_id = state.get("cancel_token_id")
    if token_id:
        _check_cancel_token(token_id)


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


def _parse_list_output(text: str) -> List[str]:
    """Parse python-list-like output into a string list."""
    if not text:
        return []
    fenced = re.findall(r"```(?:python)?(.*?)```", text, flags=re.S | re.I)
    if fenced:
        text = fenced[-1]
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = ast.literal_eval(text)
        if isinstance(data, list):
            return [str(x).strip() for x in data if isinstance(x, (str, int, float))]
    except Exception:
        pass
    # Fallback: split by newline
    return [line.strip() for line in text.splitlines() if line.strip()]


def _format_results(results: List[Dict[str, Any]]) -> str:
    """Format search results for prompt consumption."""
    blocks: List[str] = []
    for idx, r in enumerate(results, 1):
        blocks.append(
            textwrap.dedent(
                f"""\
                [{idx}]
                标题: {r.get("title") or "N/A"}
                日期: {r.get("published_date") or "unknown"}
                评分: {r.get("score", 0)}
                链接: {r.get("url") or ""}
                摘要: {r.get("summary") or r.get("snippet") or ""}
                原文: {(r.get("raw_excerpt") or "")[:500]}
                """
            ).strip()
        )
    return "\n\n".join(blocks)


def _generate_queries(
    llm: ChatOpenAI,
    topic: str,
    have_query: List[str],
    summary_notes: List[str],
    query_num: int,
    config: Dict[str, Any],
) -> List[str]:
    """Generate new search queries based on topic and existing knowledge."""
    prompt = ChatPromptTemplate.from_messages([("user", formulate_query_prompt)])
    msg = prompt.format_messages(
        topic=topic,
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
    selected_urls: List[str],  # 新增：已选择的 URL
) -> List[str]:
    """Pick relevant URLs from search results, excluding already selected ones."""
    if not results:
        return []

    # 过滤已选择的 URL
    available_results = [r for r in results if r.get("url") and r.get("url") not in selected_urls]

    if not available_results:
        logger.info("所有 URL 都已被选择过，无新 URL 可选")
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

    # Clamp
    deduped: List[str] = []
    seen = set()
    for u in urls:
        if not isinstance(u, str):
            continue
        u = u.strip()
        if not u or u in seen or u in selected_urls:
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

    reasoning_model = _selected_reasoning_model(config, settings.reasoning_model)
    primary_model = _selected_model(config, settings.primary_model)

    planner_llm = _chat_model(reasoning_model, temperature=0.8)
    critic_llm = _chat_model(reasoning_model, temperature=0.2)
    writer_llm = _chat_model(primary_model, temperature=0.5)

    have_query: List[str] = []
    summary_notes: List[str] = []
    search_runs: List[Dict[str, Any]] = []

    # ✨ 新增：URL 去重机制
    all_searched_urls: List[str] = []  # 所有搜索到的 URL
    selected_urls: List[str] = []  # 已爬取的 URL

    logger.info(f"[deepsearch] topic='{topic}' epochs={max_epochs}")
    logger.info(f"[deepsearch] 开始优化版深度搜索")

    start_ts = time.time()

    try:
        for epoch in range(max_epochs):
            try:
                _check_cancel(state)
                epoch_start = time.time()
                logger.info(f"[deepsearch] ===== Epoch {epoch + 1}/{max_epochs} =====")

                # ⏱️ Step 1: 生成查询
                query_start = time.time()
                queries = _generate_queries(
                    planner_llm, topic, have_query, summary_notes, query_num, config
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

                    # 📝 记录所有搜索到的 URL（去重）
                    for r in results:
                        url = r.get("url")
                        if url and url not in all_searched_urls:
                            all_searched_urls.append(url)

                logger.info(
                    f"[deepsearch] Epoch {epoch + 1}: 搜索到 {len(combined_results)} 个结果"
                    f" | 累计 URL: {len(all_searched_urls)}"
                    f" | 耗时 {time.time() - search_start:.2f}s"
                )

                if not combined_results:
                    logger.info(f"[deepsearch] Epoch {epoch + 1}: 无搜索结果，跳过本轮")
                    continue

                # ⏱️ Step 3: 挑选最相关的 URL（排除已选择的）
                pick_start = time.time()
                chosen_urls = _pick_relevant_urls(
                    critic_llm,
                    topic,
                    summary_notes,
                    combined_results,
                    top_urls,
                    config,
                    selected_urls,  # ✨ 传入已选择的 URL
                )

                if not chosen_urls:
                    logger.warning(
                        f"[deepsearch] Epoch {epoch + 1}: 无新 URL 可选（已全部选择过），跳过本轮"
                    )
                    continue

                # 更新已选择的 URL 列表
                selected_urls.extend(chosen_urls)

                chosen_results = [r for r in combined_results if r.get("url") in set(chosen_urls)]
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
