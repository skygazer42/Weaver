"""
Deterministic query strategy helpers for deepsearch.

Adds lightweight coverage controls so each deepsearch run explores
multiple evidence dimensions instead of relying only on LLM sampling.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

_QUERY_DIMENSIONS = (
    "freshness",
    "official",
    "evidence",
    "risk",
    "implementation",
)

_EN_TIME_MARKERS = (
    "latest",
    "recent",
    "today",
    "current",
    "update",
    "updates",
    "new",
    "this week",
    "this month",
    "news",
)

_ZH_TIME_MARKERS = (
    "最新",
    "近期",
    "今天",
    "当下",
    "更新",
    "本周",
    "本月",
    "动态",
    "新闻",
)

_OFFICIAL_MARKERS = (
    "official",
    "documentation",
    "docs",
    "release notes",
    "changelog",
    "roadmap",
    "官方",
    "文档",
    "发布说明",
    "路线图",
)

_EVIDENCE_MARKERS = (
    "benchmark",
    "evaluation",
    "metrics",
    "data",
    "report",
    "study",
    "paper",
    "评测",
    "评估",
    "指标",
    "数据",
    "报告",
    "论文",
)

_RISK_MARKERS = (
    "risk",
    "risks",
    "limitation",
    "limitations",
    "criticism",
    "criticisms",
    "tradeoff",
    "trade-offs",
    "争议",
    "风险",
    "局限",
    "缺点",
    "问题",
)

_IMPLEMENTATION_MARKERS = (
    "implementation",
    "how to",
    "best practices",
    "case study",
    "architecture",
    "playbook",
    "实践",
    "案例",
    "最佳实践",
    "架构",
    "落地",
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_YEAR_RE = re.compile(r"\b20\d{2}\b")


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


def _contains_any_raw(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _is_cjk_text(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def is_time_sensitive_topic(topic: str) -> bool:
    """Return whether a topic explicitly asks for recent/fresh information."""
    text = str(topic or "").strip()
    if not text:
        return False

    if _contains_any(text, _EN_TIME_MARKERS):
        return True
    if _contains_any_raw(text, _ZH_TIME_MARKERS):
        return True
    return bool(_YEAR_RE.search(text))


def query_dimensions(query: str) -> Set[str]:
    """Infer coverage dimensions represented by a query."""
    text = str(query or "").strip()
    if not text:
        return set()

    dims: Set[str] = set()

    if is_time_sensitive_topic(text):
        dims.add("freshness")

    if _contains_any(text, _OFFICIAL_MARKERS) or _contains_any_raw(text, _OFFICIAL_MARKERS):
        dims.add("official")

    if _contains_any(text, _EVIDENCE_MARKERS) or _contains_any_raw(text, _EVIDENCE_MARKERS):
        dims.add("evidence")

    if _contains_any(text, _RISK_MARKERS) or _contains_any_raw(text, _RISK_MARKERS):
        dims.add("risk")

    if _contains_any(text, _IMPLEMENTATION_MARKERS) or _contains_any_raw(
        text, _IMPLEMENTATION_MARKERS
    ):
        dims.add("implementation")

    return dims


def analyze_query_coverage(queries: List[str]) -> Dict[str, Any]:
    """Compute dimension coverage score for generated research queries."""
    hits = {name: 0 for name in _QUERY_DIMENSIONS}

    for query in queries or []:
        for dim in query_dimensions(query):
            if dim in hits:
                hits[dim] += 1

    covered = sorted([name for name, count in hits.items() if count > 0])
    missing = sorted([name for name in _QUERY_DIMENSIONS if hits.get(name, 0) == 0])

    score = 0.0
    if _QUERY_DIMENSIONS:
        score = round(len(covered) / len(_QUERY_DIMENSIONS), 3)

    return {
        "score": score,
        "covered_dimensions": covered,
        "missing_dimensions": missing,
        "dimension_hits": hits,
        "total_queries": len(queries or []),
    }


def _seed_templates(topic: str, year: int) -> List[Dict[str, str]]:
    if _is_cjk_text(topic):
        return [
            {"dimension": "freshness", "query": f"{topic} 最新进展 {year}"},
            {"dimension": "official", "query": f"{topic} 官方文档 发布说明"},
            {"dimension": "evidence", "query": f"{topic} 数据 报告 评测"},
            {"dimension": "risk", "query": f"{topic} 局限 风险 争议"},
            {"dimension": "implementation", "query": f"{topic} 实践 案例 最佳实践"},
        ]

    return [
        {"dimension": "freshness", "query": f"{topic} latest updates {year}"},
        {"dimension": "official", "query": f"{topic} official documentation release notes"},
        {"dimension": "evidence", "query": f"{topic} benchmark evaluation metrics"},
        {"dimension": "risk", "query": f"{topic} limitations risks tradeoffs"},
        {
            "dimension": "implementation",
            "query": f"{topic} implementation best practices case study",
        },
    ]


def backfill_diverse_queries(
    topic: str,
    existing_queries: List[str],
    historical_queries: List[str],
    query_num: int,
) -> List[str]:
    """
    Backfill query list with deterministic dimension seeds.

    Keeps existing LLM-generated queries first, only filling missing slots.
    """
    target = max(1, int(query_num or 1))

    seen = {
        str(q).strip().lower()
        for q in (historical_queries or [])
        if isinstance(q, str) and str(q).strip()
    }

    final_queries: List[str] = []
    for query in existing_queries or []:
        q = str(query or "").strip()
        if not q:
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        final_queries.append(q)
        if len(final_queries) >= target:
            return final_queries[:target]

    coverage = analyze_query_coverage(final_queries)
    missing = set(coverage.get("missing_dimensions", []))

    seeds = _seed_templates(topic=str(topic or "").strip() or "topic", year=datetime.now().year)

    prioritized = [seed for seed in seeds if seed["dimension"] in missing]
    prioritized.extend([seed for seed in seeds if seed["dimension"] not in missing])

    for seed in prioritized:
        query = seed["query"].strip()
        key = query.lower()
        if not query or key in seen:
            continue
        seen.add(key)
        final_queries.append(query)
        if len(final_queries) >= target:
            break

    return final_queries[:target]


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None

        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text

        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def summarize_freshness(search_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize freshness distribution from collected search results."""
    total_results = 0
    known_count = 0
    unknown_count = 0
    fresh_7_count = 0
    fresh_30_count = 0
    stale_180_count = 0

    now = datetime.now(timezone.utc)

    for run in search_runs or []:
        results = run.get("results") if isinstance(run, dict) else []
        if not isinstance(results, list):
            continue

        for result in results:
            total_results += 1
            published_date = result.get("published_date") if isinstance(result, dict) else None
            dt = _parse_datetime(published_date)
            if dt is None:
                unknown_count += 1
                continue

            known_count += 1
            age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
            if age_days <= 7:
                fresh_7_count += 1
            if age_days <= 30:
                fresh_30_count += 1
            if age_days > 180:
                stale_180_count += 1

    fresh_30_ratio = round(fresh_30_count / known_count, 3) if known_count else 0.0
    stale_180_ratio = round(stale_180_count / known_count, 3) if known_count else 0.0

    return {
        "total_results": total_results,
        "known_count": known_count,
        "unknown_count": unknown_count,
        "fresh_7_count": fresh_7_count,
        "fresh_30_count": fresh_30_count,
        "stale_180_count": stale_180_count,
        "fresh_30_ratio": fresh_30_ratio,
        "stale_180_ratio": stale_180_ratio,
    }
