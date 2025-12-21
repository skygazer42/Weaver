import ast
import asyncio
import json
import logging
import os
import re
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai import BadRequestError

from common.config import settings
from common.cancellation import check_cancellation as _check_cancel_token
from prompts.templates.deepsearch import (
    final_summary_prompt,
    formulate_query_prompt,
    related_url_prompt,
    summary_crawl_prompt,
    summary_text_prompt,
)
from tools.search import tavily_search
from tools.crawler import crawl_urls

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
                标题: {r.get('title') or 'N/A'}
                日期: {r.get('published_date') or 'unknown'}
                评分: {r.get('score', 0)}
                链接: {r.get('url') or ''}
                摘要: {r.get('summary') or r.get('snippet') or ''}
                原文: { (r.get('raw_excerpt') or '')[:500] }
                """
            ).strip()
        )
    return "\n\n".join(blocks)


def _generate_queries(
    llm: ChatOpenAI,
    fallback_llm: ChatOpenAI,
    topic: str,
    have_query: List[str],
    summary_notes: List[str],
    query_num: int,
    config: Dict[str, Any],
) -> List[str]:
    # Use user role to avoid providers that reject the newer "developer" role
    prompt = ChatPromptTemplate.from_messages(
        [("user", formulate_query_prompt)]
    )
    msg = prompt.format_messages(
        topic=topic,
        have_query=", ".join(have_query) or "[]",
        summary_search="\n\n".join(summary_notes) or "暂无",
        query_num=query_num,
    )
    try:
        response = llm.invoke(msg, config=config)
    except BadRequestError as e:
        if "Model Not Exist" in str(e) and fallback_llm:
            logger.warning(f"[deepsearch] planner model not found, falling back to primary: {e}")
            response = fallback_llm.invoke(msg, config=config)
        else:
            raise
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
    fallback_llm: ChatOpenAI,
    topic: str,
    summary_notes: List[str],
    results: List[Dict[str, Any]],
    max_urls: int,
    config: Dict[str, Any],
) -> List[str]:
    if not results:
        return []
    prompt = ChatPromptTemplate.from_messages([("user", related_url_prompt)])
    msg = prompt.format_messages(
        topic=topic,
        summary_search="\n\n".join(summary_notes) or "暂无",
        text=_format_results(results),
    )
    try:
        response = llm.invoke(msg, config=config)
    except BadRequestError as e:
        if "Model Not Exist" in str(e) and fallback_llm:
            logger.warning(f"[deepsearch] critic model not found, falling back to primary: {e}")
            response = fallback_llm.invoke(msg, config=config)
        else:
            raise
    urls = _parse_list_output(getattr(response, "content", "") or "")
    # Fallback: top scores
    if not urls:
        sorted_results = sorted(results, key=lambda r: r.get("score", 0), reverse=True)
        urls = [r.get("url") for r in sorted_results if r.get("url")]
    # Clamp
    deduped: List[str] = []
    seen = set()
    for u in urls:
        if not isinstance(u, str):
            continue
        u = u.strip()
        if not u or u in seen:
            continue
        seen.add(u)
        deduped.append(u)
        if len(deduped) >= max_urls:
            break
    return deduped


def _summarize_new_knowledge(
    llm: ChatOpenAI,
    fallback_llm: ChatOpenAI,
    topic: str,
    summary_notes: List[str],
    chosen_results: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> Tuple[bool, str]:
    if not chosen_results:
        return False, ""

    prompt = ChatPromptTemplate.from_messages([("user", summary_crawl_prompt)])
    msg = prompt.format_messages(
        summary_search="\n\n".join(summary_notes) or "暂无",
        crawl_res=_format_results(chosen_results),
        topic=topic,
    )
    try:
        response = llm.invoke(msg, config=config)
    except BadRequestError as e:
        if "Model Not Exist" in str(e) and fallback_llm:
            logger.warning(f"[deepsearch] critic model not found (summarize), fallback to primary: {e}")
            response = fallback_llm.invoke(msg, config=config)
        else:
            raise
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
    prompt = ChatPromptTemplate.from_messages([("user", final_summary_prompt)])
    msg = prompt.format_messages(
        topic=topic,
        summary_search="\n\n".join(summary_notes) or "暂无",
    )
    response = llm.invoke(msg, config=config)
    return getattr(response, "content", "") or summary_text_prompt


def _hydrate_with_crawler(results: List[Dict[str, Any]]) -> None:
    """
    Enrich results in-place with crawled content when Tavily lacks body text.
    """
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
            "mode": "deepsearch",
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"[deepsearch] saved run data -> {path}")
        return str(path)
    except Exception as e:
        logger.warning(f"[deepsearch] failed to save data: {e}")
        return ""


def run_deepsearch(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Iterative deep-search pipeline inspired by the reference deepsearch project.
    """
    topic = state.get("input", "")
    _check_cancel(state)

    max_epochs = int(getattr(settings, "deepsearch_max_epochs", 3))
    query_num = int(getattr(settings, "deepsearch_query_num", 5))
    per_query_results = int(getattr(settings, "deepsearch_results_per_query", 5))
    top_urls = max(3, min(5, per_query_results))

    reasoning_model = _selected_reasoning_model(config, settings.reasoning_model)
    primary_model = _selected_model(config, settings.primary_model)

    # DeepSeek/base-url specific fallback: if reasoning model is not available on the provider, reuse primary
    if settings.openai_base_url and "deepseek.com" in settings.openai_base_url.lower():
        if reasoning_model == "o1-mini":
            reasoning_model = primary_model

    planner_llm = _chat_model(reasoning_model, temperature=0.8)
    critic_llm = _chat_model(reasoning_model, temperature=0.2)
    writer_llm = _chat_model(primary_model, temperature=0.5)
    fallback_llm = writer_llm

    have_query: List[str] = []
    summary_notes: List[str] = []
    search_runs: List[Dict[str, Any]] = []

    logger.info(f"[deepsearch] topic='{topic}' epochs={max_epochs}")

    start_ts = time.time()
    for epoch in range(max_epochs):
        _check_cancel(state)
        logger.info(f"[deepsearch] epoch {epoch + 1}/{max_epochs}")

        queries = _generate_queries(
            planner_llm, fallback_llm, topic, have_query, summary_notes, query_num, config
        )
        if epoch == 0 and topic not in queries:
            queries.append(topic)
        if not queries:
            queries = [topic]
        have_query.extend(q for q in queries if q not in have_query)

        # Search
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

        if not combined_results:
            logger.info("[deepsearch] no results this epoch; continuing")
            continue

        # Pick most relevant URLs and summarize
        chosen_urls = _pick_relevant_urls(
            critic_llm, fallback_llm, topic, summary_notes, combined_results, top_urls, config
        )
        chosen_results = [
            r for r in combined_results if r.get("url") in set(chosen_urls)
        ]
        if not chosen_results:
            chosen_results = sorted(
                combined_results, key=lambda r: r.get("score", 0), reverse=True
            )[:top_urls]

        # Fallback crawl to enrich missing bodies
        _hydrate_with_crawler(chosen_results)

        enough, summary_text = _summarize_new_knowledge(
            critic_llm, fallback_llm, topic, summary_notes, chosen_results, config
        )
        if summary_text:
            summary_notes.append(summary_text)

        logger.info(
            f"[deepsearch] epoch {epoch + 1} summary_len={len(summary_text)} enough={enough}"
        )
        if enough:
            break

    final_report = (
        _final_report(writer_llm, topic, summary_notes, config)
        if summary_notes
        else summary_text_prompt
    )
    elapsed = time.time() - start_ts
    logger.info(f"[deepsearch] done in {elapsed:.2f}s, summaries={len(summary_notes)}")

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
        messages.append(AIMessage(content=f"(已保存本次深搜数据：{save_path})"))

    return {
        "research_plan": have_query,
        "scraped_content": search_runs,
        "draft_report": final_report,
        "final_report": final_report,
        "messages": messages,
        "is_complete": False,
    }
