from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse

import httpx

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_title(html: str) -> str:
    if not html:
        return ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    if not m:
        return ""
    title = re.sub(r"\s+", " ", m.group(1)).strip()
    return title[:200]


def _strip_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?>.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"<noscript.*?>.*?</noscript>", "", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_links(html: str, base_url: str, limit: int = 30) -> List[Dict[str, str]]:
    if not html:
        return []
    links: List[Dict[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(
        r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html, flags=re.I | re.S
    ):
        href = (m.group(1) or "").strip()
        if not href or href.startswith("#"):
            continue
        if href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue

        text = re.sub(r"<[^>]+>", " ", (m.group(2) or ""))
        text = re.sub(r"\s+", " ", text).strip()

        abs_url = urljoin(base_url, href)
        # Skip non-http(s)
        scheme = urlparse(abs_url).scheme.lower()
        if scheme not in {"http", "https"}:
            continue
        if abs_url in seen:
            continue
        seen.add(abs_url)
        links.append({"text": text[:200], "url": abs_url})
        if len(links) >= limit:
            break
    return links


@dataclass
class BrowserPage:
    url: str
    title: str
    text: str
    links: List[Dict[str, str]]
    fetched_at: str


class BrowserSession:
    """
    Very lightweight, JS-free “browser” session:
    - fetches pages over HTTP
    - extracts title/text/links
    - maintains simple back history
    """

    def __init__(self, *, timeout_s: float = 20.0):
        self.timeout_s = timeout_s
        self.current: Optional[BrowserPage] = None
        self.history: List[BrowserPage] = []

    def navigate(self, url: str) -> BrowserPage:
        url = (url or "").strip()
        if not url:
            raise ValueError("url is required")

        headers = {"User-Agent": DEFAULT_UA}
        with httpx.Client(timeout=self.timeout_s, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text or ""

        title = _extract_title(html)
        text = _strip_html(html)
        links = _extract_links(html, str(resp.url))
        page = BrowserPage(
            url=str(resp.url), title=title, text=text, links=links, fetched_at=_utc_now_iso()
        )

        if self.current is not None:
            self.history.append(self.current)
        self.current = page
        return page

    def back(self) -> BrowserPage:
        if not self.history:
            raise ValueError("No history to go back to")
        self.current = self.history.pop()
        return self.current

    def search(self, query: str, *, engine: str = "duckduckgo") -> BrowserPage:
        query = (query or "").strip()
        if not query:
            raise ValueError("query is required")
        engine = (engine or "duckduckgo").strip().lower()

        if engine in {"ddg", "duckduckgo", "duck"}:
            # HTML endpoint (more scrape-friendly than JS UI)
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        elif engine in {"bing"}:
            url = f"https://www.bing.com/search?q={quote_plus(query)}"
        else:
            raise ValueError(f"Unsupported engine: {engine}")

        return self.navigate(url)


class BrowserSessionManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: Dict[str, BrowserSession] = {}

    def get(self, thread_id: str) -> BrowserSession:
        thread_id = (thread_id or "").strip() or "default"
        with self._lock:
            if thread_id not in self._sessions:
                self._sessions[thread_id] = BrowserSession()
            return self._sessions[thread_id]

    def reset(self, thread_id: str) -> None:
        thread_id = (thread_id or "").strip() or "default"
        with self._lock:
            self._sessions.pop(thread_id, None)


browser_sessions = BrowserSessionManager()
