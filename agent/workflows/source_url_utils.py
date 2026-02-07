from typing import Any, Dict, List
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "ref",
    "ref_src",
    "mc_cid",
    "mc_eid",
}


def canonicalize_source_url(raw_url: Any) -> str:
    url = str(raw_url or "").strip()
    if not url:
        return ""
    try:
        parsed = urlsplit(url)
    except Exception:
        return url
    if not parsed.scheme or not parsed.netloc:
        return url

    normalized_query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if str(k).lower() not in TRACKING_QUERY_KEYS
        ],
        doseq=True,
    )
    normalized_path = parsed.path.rstrip("/")
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            normalized_path,
            normalized_query,
            "",
        )
    )


def compact_unique_sources(results: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    compact: List[Dict[str, Any]] = []
    seen_urls = set()
    for item in results or []:
        if not isinstance(item, dict):
            continue
        canonical_url = canonicalize_source_url(item.get("url"))
        if not canonical_url or canonical_url in seen_urls:
            continue
        seen_urls.add(canonical_url)
        compact.append(
            {
                "title": item.get("title", ""),
                "url": canonical_url,
                "provider": item.get("provider", ""),
                "published_date": item.get("published_date"),
                "score": float(item.get("score", 0.0) or 0.0),
            }
        )
        if len(compact) >= max(1, int(limit)):
            break
    return compact
