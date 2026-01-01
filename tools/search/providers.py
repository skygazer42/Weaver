"""
Multi-provider web search (API-based).

This is adapted from Shannon's `llm_service/tools/builtin/web_search.py`, but implemented
with Weaver's settings and sync `requests` calls so it can be used inside LangChain tools.

Why this exists:
- Directly opening Google/Bing/DuckDuckGo in Playwright often triggers anti-bot challenges.
- API search providers (Serper/SerpAPI/Bing/Exa/Firecrawl/Google CSE) are far more stable.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import requests

from common.config import settings

logger = logging.getLogger(__name__)


DEFAULT_TIMEOUT_S = 20


def _is_valid_api_key(api_key: str) -> bool:
    if not api_key or not isinstance(api_key, str):
        return False
    api_key = api_key.strip()
    if len(api_key) < 10:
        return False
    if api_key.lower() in {"test", "demo", "example", "your_api_key_here", "xxx"}:
        return False
    return True


def _sanitize_error_message(error: str) -> str:
    sanitized = str(error)
    sanitized = re.sub(r"https?://[^\s]+", "[URL_REDACTED]", sanitized)
    sanitized = re.sub(r"\b[A-Za-z0-9]{32,}\b", "[KEY_REDACTED]", sanitized)
    sanitized = re.sub(
        r"api[_\-]?key[\s=:]+[\w\-]+",
        "api_key=[REDACTED]",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(r"bearer\s+[\w\-\.]+", "Bearer [REDACTED]", sanitized, flags=re.IGNORECASE)
    if len(sanitized) > 300:
        sanitized = sanitized[:300] + "..."
    return sanitized


def _safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return None


def serper_search(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    api_key = (getattr(settings, "serper_api_key", "") or "").strip()
    if not _is_valid_api_key(api_key):
        return []

    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": int(max_results or 10)}

    resp = requests.post(url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT_S)
    if resp.status_code != 200:
        msg = _sanitize_error_message(resp.text)
        raise RuntimeError(f"Serper API error ({resp.status_code}): {msg}")

    data = _safe_json(resp) or {}
    results: List[Dict[str, Any]] = []

    kg = data.get("knowledgeGraph")
    if isinstance(kg, dict) and (kg.get("title") or kg.get("description") or kg.get("website")):
        results.append(
            {
                "title": kg.get("title", "") or "",
                "snippet": kg.get("description", "") or "",
                "url": kg.get("website", "") or "",
                "source": "serper_knowledge_graph",
                "type": kg.get("type", ""),
                "position": 0,
            }
        )

    organic = data.get("organic") or []
    if isinstance(organic, list):
        for idx, item in enumerate(organic, 1):
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": item.get("title", "") or "",
                    "snippet": item.get("snippet", "") or "",
                    "url": item.get("link", "") or "",
                    "source": "serper",
                    "position": int(item.get("position") or idx),
                    "date": item.get("date"),
                }
            )

    return results[: int(max_results or 10)]


def serpapi_search(query: str, max_results: int = 10, *, engine: str = "google") -> List[Dict[str, Any]]:
    api_key = (getattr(settings, "serpapi_api_key", "") or "").strip()
    if not _is_valid_api_key(api_key):
        return []

    url = "https://serpapi.com/search.json"
    params = {
        "engine": (engine or "google").strip().lower(),
        "q": query,
        "api_key": api_key,
        "num": max(1, min(int(max_results or 10), 100)),
    }

    resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT_S)
    if resp.status_code != 200:
        msg = _sanitize_error_message(resp.text)
        raise RuntimeError(f"SerpAPI error ({resp.status_code}): {msg}")

    data = _safe_json(resp) or {}
    results: List[Dict[str, Any]] = []

    kg = data.get("knowledge_graph")
    if isinstance(kg, dict) and (kg.get("title") or kg.get("description")):
        kg_url = ""
        kg_source = kg.get("source")
        if isinstance(kg_source, dict):
            kg_url = kg_source.get("link", "") or ""
        elif isinstance(kg_source, str):
            kg_url = kg_source
        results.append(
            {
                "title": kg.get("title", "") or "",
                "snippet": kg.get("description", "") or "",
                "url": kg_url,
                "source": "serpapi_knowledge_graph",
                "type": kg.get("type", ""),
                "position": 0,
            }
        )

    organic = data.get("organic_results") or []
    if isinstance(organic, list):
        for idx, item in enumerate(organic, 1):
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": item.get("title", "") or "",
                    "snippet": item.get("snippet", "") or "",
                    "url": item.get("link", "") or "",
                    "source": "serpapi",
                    "position": int(item.get("position") or idx),
                    "date": item.get("date"),
                }
            )

    return results[: int(max_results or 10)]


def bing_search(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    api_key = (getattr(settings, "bing_api_key", "") or "").strip()
    if not _is_valid_api_key(api_key):
        return []

    url = "https://api.cognitive.microsoft.com/bing/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {
        "q": query,
        "count": max(1, min(int(max_results or 10), 50)),
        "textDecorations": True,
        "textFormat": "HTML",
    }

    resp = requests.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT_S)
    if resp.status_code != 200:
        msg = _sanitize_error_message(resp.text)
        raise RuntimeError(f"Bing Search API error ({resp.status_code}): {msg}")

    data = _safe_json(resp) or {}
    results: List[Dict[str, Any]] = []

    web_pages = data.get("webPages") if isinstance(data, dict) else None
    values = web_pages.get("value") if isinstance(web_pages, dict) else None
    if isinstance(values, list):
        for idx, item in enumerate(values, 1):
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": item.get("name", "") or "",
                    "snippet": item.get("snippet", "") or "",
                    "url": item.get("url", "") or "",
                    "source": "bing",
                    "position": idx,
                    "date": item.get("dateLastCrawled"),
                }
            )

    return results[: int(max_results or 10)]


def google_cse_search(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    api_key = (getattr(settings, "google_search_api_key", "") or "").strip()
    search_engine_id = (getattr(settings, "google_search_engine_id", "") or "").strip()
    if not (_is_valid_api_key(api_key) and search_engine_id):
        return []

    url = "https://customsearch.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": search_engine_id,
        "q": query,
        "num": min(max(1, int(max_results or 10)), 10),
    }

    resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT_S)
    if resp.status_code != 200:
        msg = _sanitize_error_message(resp.text)
        raise RuntimeError(f"Google CSE API error ({resp.status_code}): {msg}")

    data = _safe_json(resp) or {}
    results: List[Dict[str, Any]] = []

    items = data.get("items") or []
    if isinstance(items, list):
        for idx, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            snippet = item.get("snippet", "") or ""
            content = snippet
            page_map = item.get("pagemap") or {}
            if isinstance(page_map, dict):
                metatags = page_map.get("metatags")
                if isinstance(metatags, list) and metatags and isinstance(metatags[0], dict):
                    mt = metatags[0]
                    content = (mt.get("og:description") or mt.get("description") or content) or ""
                    content = content[:500]

            results.append(
                {
                    "title": item.get("title", "") or "",
                    "snippet": snippet,
                    "url": item.get("link", "") or "",
                    "source": "google_cse",
                    "position": idx,
                    "display_link": item.get("displayLink", ""),
                    "content": content,
                }
            )

    return results[: int(max_results or 10)]


def exa_search(
    query: str,
    max_results: int = 10,
    *,
    search_type: str = "auto",
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    api_key = (getattr(settings, "exa_api_key", "") or "").strip()
    if not _is_valid_api_key(api_key):
        return []

    url = "https://api.exa.ai/search"
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    search_type_norm = (search_type or "auto").strip().lower()
    if search_type_norm not in {"neural", "keyword", "auto"}:
        search_type_norm = "auto"

    payload: Dict[str, Any] = {
        "query": query,
        "numResults": max(1, min(int(max_results or 10), 100)),
        "type": search_type_norm,
        "useAutoprompt": True,
        "contents": {
            "text": {"maxCharacters": 2000, "includeHtmlTags": False},
            "highlights": {"numSentences": 3, "highlightsPerUrl": 2},
        },
        "liveCrawl": "fallback",
    }
    if category:
        payload["category"] = category

    resp = requests.post(url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT_S)
    if resp.status_code != 200:
        msg = _sanitize_error_message(resp.text)
        raise RuntimeError(f"Exa API error ({resp.status_code}): {msg}")

    data = _safe_json(resp) or {}
    results: List[Dict[str, Any]] = []

    items = data.get("results") or []
    if isinstance(items, list):
        for idx, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            highlights = item.get("highlights") or []
            snippet = ""
            if isinstance(highlights, list):
                parts = [h.strip() for h in highlights if isinstance(h, str) and h.strip()]
                snippet = " ... ".join(parts)[:500]
            if not snippet:
                snippet = (item.get("text", "") or "")[:500]

            results.append(
                {
                    "title": item.get("title", "") or "",
                    "snippet": snippet,
                    "url": item.get("url", "") or "",
                    "source": "exa",
                    "position": idx,
                    "score": item.get("score", 0),
                    "published_date": item.get("publishedDate"),
                    "author": item.get("author"),
                    "highlights": highlights,
                }
            )

    return results[: int(max_results or 10)]


def firecrawl_search(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    api_key = (getattr(settings, "firecrawl_api_key", "") or "").strip()
    if not _is_valid_api_key(api_key):
        return []

    url = "https://api.firecrawl.dev/v2/search"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "query": query,
        "limit": min(max(1, int(max_results or 10)), 20),
        "sources": ["web"],
        "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT_S)
    if resp.status_code != 200:
        msg = _sanitize_error_message(resp.text)
        raise RuntimeError(f"Firecrawl API error ({resp.status_code}): {msg}")

    data = _safe_json(resp) or {}
    results: List[Dict[str, Any]] = []

    items = data.get("data") or []
    if isinstance(items, list):
        for idx, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            content = ""
            if item.get("markdown"):
                content = str(item.get("markdown") or "")[:300]
            elif item.get("description"):
                content = str(item.get("description") or "")

            results.append(
                {
                    "title": item.get("title", "") or "",
                    "snippet": content,
                    "url": item.get("url", "") or "",
                    "source": "firecrawl",
                    "position": idx,
                    "markdown": item.get("markdown", "") or "",
                }
            )

    return results[: int(max_results or 10)]

