"""
Canonical source registry for stable URL normalization and deduplication.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
}


@dataclass
class SourceRecord:
    source_id: str
    canonical_url: str
    original_url: str
    domain: str
    title: str = ""


class SourceRegistry:
    """Tracks canonicalized sources and emits stable source ids."""

    def __init__(self) -> None:
        self._by_canonical: Dict[str, SourceRecord] = {}

    def canonicalize_url(self, url: str) -> str:
        raw = (url or "").strip()
        if not raw:
            return ""
        if "://" not in raw:
            raw = f"https://{raw}"

        parsed = urlsplit(raw)
        scheme = (parsed.scheme or "https").lower()
        netloc = parsed.netloc.lower()

        if ":" in netloc:
            host, port = netloc.rsplit(":", 1)
            if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
                netloc = host

        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/")
            if not path:
                path = "/"

        query_items: List[Tuple[str, str]] = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            normalized_key = key.strip().lower()
            if normalized_key.startswith("utm_"):
                continue
            if normalized_key in _TRACKING_PARAMS:
                continue
            query_items.append((key, value))
        query_items.sort()
        query = urlencode(query_items, doseq=True)

        return urlunsplit((scheme, netloc, path, query, ""))

    def source_id_for_url(self, canonical_url: str) -> str:
        digest = hashlib.sha1(canonical_url.encode("utf-8")).hexdigest()
        return f"src_{digest[:12]}"

    def register(self, url: str, title: str = "") -> Optional[SourceRecord]:
        canonical_url = self.canonicalize_url(url)
        if not canonical_url:
            return None
        if canonical_url in self._by_canonical:
            record = self._by_canonical[canonical_url]
            if title and not record.title:
                record.title = title
            return record

        parsed = urlsplit(canonical_url)
        record = SourceRecord(
            source_id=self.source_id_for_url(canonical_url),
            canonical_url=canonical_url,
            original_url=url,
            domain=parsed.netloc,
            title=title,
        )
        self._by_canonical[canonical_url] = record
        return record

    def get(self, url: str) -> Optional[SourceRecord]:
        canonical_url = self.canonicalize_url(url)
        if not canonical_url:
            return None
        return self._by_canonical.get(canonical_url)

    def all(self) -> List[SourceRecord]:
        return list(self._by_canonical.values())
