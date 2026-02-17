from __future__ import annotations

import html
import ipaddress
import re
import threading
from datetime import datetime, timezone
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


def _html_to_markdown(html: str) -> str:
    if not html:
        return ""
    try:
        from markdownify import markdownify as _markdownify

        return str(_markdownify(html) or "").strip()
    except Exception:
        return ""


def _extract_title_from_html(text: str) -> str:
    if not text:
        return ""

    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.S | re.I)
    if title_match:
        raw = title_match.group(1)
        return html.unescape(_strip_html(raw)).strip()

    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", text, flags=re.S | re.I)
    if h1_match:
        raw = h1_match.group(1)
        return html.unescape(_strip_html(raw)).strip()

    return ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _looks_like_javascript_interstitial(text: str) -> bool:
    if not text:
        return False

    lowered = str(text).lower()
    if "enable javascript" in lowered and ("continue" in lowered or "cookies" in lowered):
        return True
    if "please enable javascript" in lowered:
        return True
    if "checking your browser" in lowered and ("before accessing" in lowered or "before you access" in lowered):
        return True
    if "just a moment" in lowered and "checking your browser" in lowered:
        return True
    if "verify you are human" in lowered:
        return True

    return False


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


def _extract_body_from_response(resp: object) -> tuple[str, Optional[str], Optional[str], Optional[int], str]:
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

    markdown: Optional[str] = None
    if "html" in content_type:
        title = _extract_title_from_html(decoded) or None
        text = _strip_html(decoded)
        if bool(getattr(settings, "research_fetch_extract_markdown", True)):
            md = _html_to_markdown(decoded)
            markdown = md or None
        return text, markdown, title, status_code, content_type

    return decoded, None, None, status_code, content_type


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

    def _fetch_via_reader(self, canonical_url: str, raw_url: str, *, attempts: int) -> Optional[FetchedPage]:
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
                stream=True,
            )
        except Exception:
            return None

        try:
            text, markdown, title, status_code, _content_type = _extract_body_from_response(resp)
        finally:
            closer = getattr(resp, "close", None)
            if callable(closer):
                closer()
        if status_code == 200 and (text or "").strip():
            return FetchedPage(
                url=canonical_url,
                raw_url=raw_url,
                method=self._reader_method_label(),
                text=text,
                title=title,
                markdown=markdown,
                http_status=status_code,
                attempts=attempts,
                retrieved_at=_now_iso(),
            )
        return None

    def _fetch_via_crawler(self, canonical_url: str, raw_url: str, *, attempts: int) -> Optional[FetchedPage]:
        mode = str(getattr(settings, "research_fetch_render_mode", "off") or "off").strip().lower()
        if mode == "off":
            return None

        min_chars = int(getattr(settings, "research_fetch_render_min_chars", 200) or 200)
        try:
            from tools.crawl.crawler import crawl_urls
        except Exception:
            return None

        try:
            timeout_s = max(1, int(getattr(settings, "research_fetch_timeout_s", 25.0) or 25.0))
        except Exception:
            timeout_s = 25

        try:
            results = crawl_urls([canonical_url], timeout=timeout_s)
        except Exception:
            return None

        if not isinstance(results, list) or not results:
            return None

        first = results[0] if isinstance(results[0], dict) else {}
        content = first.get("content") if isinstance(first, dict) else ""
        text = str(content or "").strip()
        if not text:
            return None
        lowered = text.lower()
        if lowered.startswith("crawl failed") or lowered.startswith("exception:"):
            return None
        if len(text) < max(1, min_chars) and mode != "always":
            return None

        return FetchedPage(
            url=canonical_url,
            raw_url=raw_url,
            method="render_crawler",
            text=text,
            http_status=200,
            attempts=attempts,
            retrieved_at=_now_iso(),
        )

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

        def _maybe_cache(page: FetchedPage) -> None:
            if cache is None or not cache_key:
                return
            store_errors = bool(getattr(settings, "research_fetch_cache_store_errors", False))
            if (page.http_status == 200 and (page.text or page.markdown)) or (store_errors and page.error):
                cache.set(cache_key, page)

        try:
            resp = requests.get(
                canonical_url,
                timeout=settings.research_fetch_timeout_s,
                headers={"User-Agent": DEFAULT_UA},
                stream=True,
            )
        except Exception as exc:
            direct_attempt.error = str(exc)
            direct_attempt.retrieved_at = _now_iso()
            render_attempt = self._fetch_via_crawler(canonical_url, raw_url, attempts=2)
            if render_attempt:
                _maybe_cache(render_attempt)
                return render_attempt

            reader_attempt = self._fetch_via_reader(canonical_url, raw_url, attempts=2)
            final = reader_attempt or direct_attempt
            _maybe_cache(final)
            return final

        try:
            text, markdown, title, status_code, content_type = _extract_body_from_response(resp)
        finally:
            closer = getattr(resp, "close", None)
            if callable(closer):
                closer()

        direct_attempt.text = text or None
        direct_attempt.title = title
        direct_attempt.markdown = markdown
        direct_attempt.http_status = status_code
        direct_attempt.retrieved_at = _now_iso()

        render_mode = str(getattr(settings, "research_fetch_render_mode", "off") or "off").strip().lower()
        min_chars = int(getattr(settings, "research_fetch_render_min_chars", 200) or 200)

        if status_code == 200 and (text or "").strip():
            if render_mode != "off" and "html" in content_type and _looks_like_javascript_interstitial(text):
                render_attempt = self._fetch_via_crawler(canonical_url, raw_url, attempts=2)
                if render_attempt:
                    _maybe_cache(render_attempt)
                    return render_attempt

            if (
                render_mode != "off"
                and "html" in content_type
                and len((text or "").strip()) < max(1, min_chars)
            ):
                render_attempt = self._fetch_via_crawler(canonical_url, raw_url, attempts=2)
                if render_attempt:
                    _maybe_cache(render_attempt)
                    return render_attempt
            _maybe_cache(direct_attempt)
            return direct_attempt

        if render_mode != "off" and ("html" in content_type or status_code != 200):
            render_attempt = self._fetch_via_crawler(canonical_url, raw_url, attempts=2)
            if render_attempt:
                _maybe_cache(render_attempt)
                return render_attempt

        reader_attempt = self._fetch_via_reader(canonical_url, raw_url, attempts=2)
        final = reader_attempt or direct_attempt
        _maybe_cache(final)
        return final

    def fetch_many(self, urls: list[str]) -> list[FetchedPage]:
        candidates: list[str] = []
        seen: set[str] = set()
        for raw in urls or []:
            canonical = self._registry.canonicalize_url(str(raw or "").strip())
            if not canonical or canonical in seen:
                continue
            seen.add(canonical)
            candidates.append(canonical)

        if not candidates:
            return []

        try:
            max_workers = max(1, int(getattr(settings, "research_fetch_concurrency", 6) or 6))
        except Exception:
            max_workers = 6

        try:
            per_domain = int(getattr(settings, "research_fetch_concurrency_per_domain", 2) or 2)
        except Exception:
            per_domain = 2

        if per_domain <= 0:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                return list(executor.map(self.fetch, candidates))

        sem_lock = threading.RLock()
        semaphores: dict[str, threading.Semaphore] = {}

        def _semaphore_for(domain: str) -> threading.Semaphore:
            with sem_lock:
                sem = semaphores.get(domain)
                if sem is None:
                    sem = threading.Semaphore(per_domain)
                    semaphores[domain] = sem
                return sem

        def _fetch_with_domain_limit(target_url: str) -> FetchedPage:
            domain = urlsplit(target_url).netloc.lower()
            sem = _semaphore_for(domain)
            sem.acquire()
            try:
                return self.fetch(target_url)
            finally:
                sem.release()

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(_fetch_with_domain_limit, candidates))
