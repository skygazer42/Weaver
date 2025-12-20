from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .crawler import crawl_url as _crawl_url
from .crawler import crawl_urls as _crawl_urls


def _trim(text: str, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


class CrawlUrlInput(BaseModel):
    url: str = Field(min_length=1)
    timeout: int = Field(default=10, ge=1, le=60)
    max_chars: int = Field(default=4000, ge=200, le=20000)


class CrawlUrlTool(BaseTool):
    name: str = "crawl_url"
    description: str = "Fetch a webpage over HTTP and return extracted plain text."
    args_schema: type[BaseModel] = CrawlUrlInput

    def _run(self, url: str, timeout: int = 10, max_chars: int = 4000) -> Dict[str, Any]:
        res = _crawl_url(url, timeout=int(timeout))
        return {"url": res.get("url", url), "content": _trim(res.get("content", ""), int(max_chars))}


class CrawlUrlsInput(BaseModel):
    urls: List[str] = Field(description="List of URLs to crawl")
    timeout: int = Field(default=10, ge=1, le=60)
    max_chars_per_url: int = Field(default=2000, ge=200, le=20000)


class CrawlUrlsTool(BaseTool):
    name: str = "crawl_urls"
    description: str = "Fetch multiple webpages (sequentially) and return extracted plain text."
    args_schema: type[BaseModel] = CrawlUrlsInput

    def _run(self, urls: List[str], timeout: int = 10, max_chars_per_url: int = 2000) -> List[Dict[str, Any]]:
        urls = [u for u in (urls or []) if isinstance(u, str) and u.strip()]
        results = _crawl_urls(urls, timeout=int(timeout))
        trimmed: List[Dict[str, Any]] = []
        for r in results:
            trimmed.append({
                "url": r.get("url", ""),
                "content": _trim(r.get("content", ""), int(max_chars_per_url)),
            })
        return trimmed


def build_crawl_tools() -> List[BaseTool]:
    return [CrawlUrlTool(), CrawlUrlsTool()]
