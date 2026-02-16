from __future__ import annotations

import ipaddress
import re
from typing import Optional
from urllib.parse import urlsplit

import requests

from agent.workflows.source_registry import SourceRegistry
from common.config import settings
from tools.research.models import FetchedPage, truncate_bytes

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def _strip_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?>.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"<noscript.*?>.*?</noscript>", "", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _content_type(headers: object) -> str:
    if not headers:
        return ""
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return ""
    try:
        value = getter("content-type") or getter("Content-Type") or getter("CONTENT-TYPE")
    except Exception:
        return ""
    return str(value) if value else ""


def _is_blocked_fetch_target(url: str) -> bool:
    parsed = urlsplit(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return True

    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        return True
    if host in {"localhost"}:
        return True

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False

    return bool(
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


class ContentFetcher:
    def __init__(self) -> None:
        self._registry = SourceRegistry()

    def fetch(self, url: str) -> FetchedPage:
        raw_url = (url or "").strip()
        canonical_url = self._registry.canonicalize_url(raw_url)
        if not canonical_url:
            return FetchedPage(
                url="",
                raw_url=raw_url,
                method="direct_http",
                error="url is required",
                attempts=1,
            )
        if _is_blocked_fetch_target(canonical_url):
            return FetchedPage(
                url=canonical_url,
                raw_url=raw_url,
                method="direct_http",
                error="blocked fetch target url",
                attempts=1,
            )

        try:
            resp = requests.get(
                canonical_url,
                timeout=settings.research_fetch_timeout_s,
                headers={"User-Agent": DEFAULT_UA},
            )
        except Exception as exc:
            return FetchedPage(
                url=canonical_url,
                raw_url=raw_url,
                method="direct_http",
                error=str(exc),
                attempts=1,
            )

        status_code: Optional[int]
        try:
            status_code = int(getattr(resp, "status_code", None))
        except Exception:
            status_code = None

        headers = getattr(resp, "headers", None)
        content_type = _content_type(headers).lower()

        raw_bytes = getattr(resp, "content", b"") or b""
        raw_bytes = truncate_bytes(raw_bytes, max_bytes=settings.research_fetch_max_bytes)

        decoded = ""
        if raw_bytes:
            decoded = raw_bytes.decode("utf-8", errors="replace")
        else:
            decoded = str(getattr(resp, "text", "") or "")

        text = decoded
        if "html" in content_type:
            text = _strip_html(decoded)

        return FetchedPage(
            url=canonical_url,
            raw_url=raw_url,
            method="direct_http",
            text=text or None,
            http_status=status_code,
            attempts=1,
        )
