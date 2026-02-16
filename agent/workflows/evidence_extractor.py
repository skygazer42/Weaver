from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.workflows.source_registry import SourceRegistry


def _pick_first_string(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_message_sources(scraped_content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Extract a stable, canonicalized list of sources from `scraped_content`.

    Expected scraped_content shape:
      - [{"query": "...", "results": [{"title": "...", "url": "...", ...}, ...]}, ...]
      - or mixed dicts that may already include "url"/"title"

    Output shape (minimal, forward-compatible):
      - title: str
      - url: str (canonicalized)
      - rawUrl?: str
      - domain?: str
      - provider?: str
      - publishedDate?: str
    """
    registry = SourceRegistry()
    sources: List[Dict[str, Any]] = []
    index_by_canonical: Dict[str, int] = {}

    def register_source(
        *,
        url: str,
        title: str,
        provider: str = "",
        published_date: Optional[str] = None,
    ) -> None:
        record = registry.register(url=url, title=title)
        if not record:
            return

        canonical_url = record.canonical_url
        if canonical_url not in index_by_canonical:
            index_by_canonical[canonical_url] = len(sources)
            sources.append(
                {
                    "title": record.title or title,
                    "url": canonical_url,
                    "rawUrl": url,
                    "domain": record.domain,
                    "provider": provider or None,
                    "publishedDate": published_date,
                }
            )
            return

        # Best-effort enrichment for already-registered sources.
        idx = index_by_canonical[canonical_url]
        existing = sources[idx]
        if not existing.get("title") and title:
            existing["title"] = title
        if not existing.get("provider") and provider:
            existing["provider"] = provider
        if not existing.get("publishedDate") and published_date:
            existing["publishedDate"] = published_date

    for run in scraped_content or []:
        if not isinstance(run, dict):
            continue

        # Support "flattened" source dicts.
        run_url = _pick_first_string(run.get("url"))
        run_title = _pick_first_string(run.get("title"))
        run_provider = _pick_first_string(run.get("provider"))
        run_published = _pick_first_string(run.get("published_date"), run.get("publishedDate"))

        if run_url:
            register_source(
                url=run_url,
                title=run_title,
                provider=run_provider,
                published_date=run_published or None,
            )
            continue

        results = run.get("results") or []
        if not isinstance(results, list):
            continue

        for item in results:
            if not isinstance(item, dict):
                continue
            url = _pick_first_string(item.get("url"))
            if not url:
                continue

            title = _pick_first_string(item.get("title"), run_title) or "Untitled"
            provider = _pick_first_string(item.get("provider"), run_provider)
            published = _pick_first_string(item.get("published_date"), item.get("publishedDate"), run_published)
            register_source(
                url=url,
                title=title,
                provider=provider,
                published_date=published or None,
            )

    # Remove explicit nulls for a cleaner frontend payload.
    for item in sources:
        if item.get("provider") is None:
            item.pop("provider", None)

    return sources

