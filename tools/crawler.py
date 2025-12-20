"""
Lightweight crawler used as a fallback when Tavily doesn't return page bodies.

Uses standard library urllib to avoid extra dependencies. It is best-effort and
will not raise on failure—callers should handle missing content gracefully.
"""

from typing import List, Dict
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import re
import logging

logger = logging.getLogger(__name__)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)


def _strip_html(html: str) -> str:
    """Very small HTML → text helper to keep dependencies zero."""
    if not html:
        return ""
    # Remove scripts/styles
    html = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?>.*?</style>", "", html, flags=re.S | re.I)
    # Drop tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def crawl_url(url: str, timeout: int = 10) -> Dict[str, str]:
    """
    Fetch a single URL and return plain text content.

    Returns dict with url, content; on error, content has the message.
    """
    try:
        req = Request(url, headers={"User-Agent": DEFAULT_UA})
        with urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            raw = resp.read().decode(charset, errors="ignore")
        return {"url": url, "content": _strip_html(raw)}
    except (HTTPError, URLError, Exception) as e:
        logger.warning(f"Crawl failed for {url}: {e}")
        return {"url": url, "content": f"Crawl failed: {e}"}


def crawl_urls(urls: List[str], timeout: int = 10) -> List[Dict[str, str]]:
    """Fetch multiple URLs sequentially (keep it simple to avoid resource spikes)."""
    results: List[Dict[str, str]] = []
    for u in urls:
        if not u:
            continue
        results.append(crawl_url(u, timeout=timeout))
    return results

