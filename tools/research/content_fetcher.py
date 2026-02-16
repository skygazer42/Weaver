from __future__ import annotations

import ipaddress
import re
from typing import Optional
from urllib.parse import urlsplit

import requests

from agent.workflows.source_registry import SourceRegistry
from common.config import settings
from tools.research.models import FetchedPage, truncate_bytes
from tools.research.page_cache import get_fetched_page_cache
from tools.research.reader_client import ReaderClient

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


def _read_response_bytes(resp: object) -> bytes:
    max_bytes = getattr(settings, "research_fetch_max_bytes", 0)
    try:
        limit = int(max_bytes)
    except Exception:
        limit = 0

    iterator = getattr(resp, "iter_content", None)
    if callable(iterator):
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in iterator(chunk_size=65536):
                if not chunk:
                    continue
                if not isinstance(chunk, (bytes, bytearray)):
                    chunk = str(chunk).encode("utf-8", errors="replace")
                chunk_bytes = bytes(chunk)

                if limit > 0:
                    remaining = limit - total
                    if remaining <= 0:
                        break
                    if len(chunk_bytes) > remaining:
                        chunks.append(chunk_bytes[:remaining])
                        total += remaining
                        break

                chunks.append(chunk_bytes)
                total += len(chunk_bytes)
        except Exception:
            return b""
        return b"".join(chunks)

    data = getattr(resp, "content", b"") or b""
    if isinstance(data, str):
        data = data.encode("utf-8", errors="replace")
    if not isinstance(data, (bytes, bytearray)):
        data = str(data).encode("utf-8", errors="replace")
    return truncate_bytes(bytes(data), max_bytes=limit)


def _extract_text_from_response(resp: object) -> tuple[str, Optional[int]]:
    status_code: Optional[int]
    try:
        status_code = int(getattr(resp, "status_code", None))
    except Exception:
        status_code = None

    headers = getattr(resp, "headers", None)
    content_type = _content_type(headers).lower()

    raw_bytes = _read_response_bytes(resp)

    if raw_bytes:
        decoded = raw_bytes.decode("utf-8", errors="replace")
    else:
        decoded = str(getattr(resp, "text", "") or "")

    text = _strip_html(decoded) if "html" in content_type else decoded
    return text, status_code


class ContentFetcher:
    def __init__(
        self,
        *,
        reader_mode: Optional[str] = None,
        reader_public_base: Optional[str] = None,
        reader_self_hosted_base: Optional[str] = None,
    ) -> None:
        self._registry = SourceRegistry()
        self._reader_mode = reader_mode if reader_mode is not None else settings.reader_fallback_mode
        self._reader_public_base = (
            reader_public_base if reader_public_base is not None else settings.reader_public_base
        )
        self._reader_self_hosted_base = (
            reader_self_hosted_base
            if reader_self_hosted_base is not None
            else settings.reader_self_hosted_base
        )

    def _reader_method_label(self) -> str:
        mode = (self._reader_mode or "").strip().lower()
        if mode == "public":
            return "reader_public"
        if mode == "self_hosted":
            return "reader_self_hosted"
        if mode == "both":
            return "reader_self_hosted" if self._reader_self_hosted_base else "reader_public"
        return "reader_unknown"

    def _fetch_via_reader(self, canonical_url: str, raw_url: str) -> Optional[FetchedPage]:
        try:
            client = ReaderClient(
                mode=self._reader_mode,
                public_base=self._reader_public_base,
                self_hosted_base=self._reader_self_hosted_base,
            )
            reader_url = client.build_reader_url(canonical_url)
        except Exception:
            return None

        try:
            resp = requests.get(
                reader_url,
                timeout=settings.research_fetch_timeout_s,
                headers={"User-Agent": DEFAULT_UA},
            )
        except Exception:
            return None

        text, status_code = _extract_text_from_response(resp)
        if status_code == 200 and (text or "").strip():
            return FetchedPage(
                url=canonical_url,
                raw_url=raw_url,
                method=self._reader_method_label(),
                text=text,
                http_status=status_code,
                attempts=2,
            )
        return None

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

        cache = get_fetched_page_cache()
        cache_key = ""
        if cache is not None:
            reader_mode = (self._reader_mode or "").strip().lower()
            render_mode = str(getattr(settings, "research_fetch_render_mode", "off") or "off").strip().lower()
            cache_key = f"{canonical_url}::render={render_mode}::reader={reader_mode}"
            cached = cache.get(cache_key)
            if cached and (cached.text or cached.markdown or cached.error):
                cached.raw_url = raw_url
                return cached

        direct_attempt = FetchedPage(
            url=canonical_url,
            raw_url=raw_url,
            method="direct_http",
            attempts=1,
        )

        try:
            resp = requests.get(
                canonical_url,
                timeout=settings.research_fetch_timeout_s,
                headers={"User-Agent": DEFAULT_UA},
            )
        except Exception as exc:
            direct_attempt.error = str(exc)
            reader_attempt = self._fetch_via_reader(canonical_url, raw_url)
            final = reader_attempt or direct_attempt
            if cache is not None and cache_key:
                store_errors = bool(getattr(settings, "research_fetch_cache_store_errors", False))
                if (final.http_status == 200 and (final.text or final.markdown)) or (store_errors and final.error):
                    cache.set(cache_key, final)
            return final

        text, status_code = _extract_text_from_response(resp)
        direct_attempt.text = text or None
        direct_attempt.http_status = status_code
        if status_code == 200 and (text or "").strip():
            if cache is not None and cache_key:
                cache.set(cache_key, direct_attempt)
            return direct_attempt

        reader_attempt = self._fetch_via_reader(canonical_url, raw_url)
        final = reader_attempt or direct_attempt
        if cache is not None and cache_key:
            store_errors = bool(getattr(settings, "research_fetch_cache_store_errors", False))
            if (final.http_status == 200 and (final.text or final.markdown)) or (store_errors and final.error):
                cache.set(cache_key, final)
        return final
