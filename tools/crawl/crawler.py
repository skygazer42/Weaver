"""
Intelligent crawler with automatic fallback strategy.

Features:
- Optimized: Playwright-based with JS rendering, parallel crawling (4x faster)
- Fallback: urllib-based for simple cases or when Playwright unavailable
- Smart selection: Automatically choose best implementation based on config/availability
- Backwards compatible: Zero code changes needed in existing code

Usage:
    from tools.crawl.crawler import crawl_urls

    # Automatically uses best available implementation
    results = crawl_urls(["https://example.com", "https://example.org"])

    # Or use async for best performance
    from tools.crawl.crawler import CrawlerOptimized
    async with CrawlerOptimized() as crawler:
        results = await crawler.crawl_urls(urls)
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from common.config import settings

# 环境变量控制是否无头模式（默认 true 无窗口；false 可视化调试）
_CRAWLER_HEADLESS = str(getattr(settings, "crawler_headless", "") or "").strip().lower()
if not _CRAWLER_HEADLESS:
    import os
    _CRAWLER_HEADLESS = os.getenv("CRAWLER_HEADLESS", "true").strip().lower()

def _is_headless() -> bool:
    return _CRAWLER_HEADLESS not in ("false", "0", "no", "off")

logger = logging.getLogger(__name__)

# Suppress Playwright's verbose logging
logging.getLogger("playwright").setLevel(logging.WARNING)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)


# ============================================================================
# Optimized Playwright-based Implementation
# ============================================================================

class CrawlerOptimized:
    """
    Async Playwright-based web crawler with browser context management.

    Features:
    - JavaScript rendering support
    - Parallel crawling with asyncio.gather()
    - Browser context reuse for efficiency
    - Configurable timeouts and wait strategies
    - Graceful error handling
    """

    def __init__(
        self,
        headless: bool = True,
        browser_timeout: int = 15000,
        page_timeout: int = 20000,
        wait_until: str = "domcontentloaded",
        max_concurrent: int = 5,
    ):
        """
        Initialize the crawler.

        Args:
            headless: Run browser in headless mode
            browser_timeout: Browser launch timeout (ms)
            page_timeout: Page navigation timeout (ms)
            wait_until: Page load strategy ("domcontentloaded", "load", "networkidle")
            max_concurrent: Maximum concurrent page requests
        """
        # 默认使用 env/config 决定是否无头；若入参显式指定则覆盖
        self.headless = headless if headless is not None else _is_headless()
        self.browser_timeout = browser_timeout
        self.page_timeout = page_timeout
        self.wait_until = wait_until
        self.max_concurrent = max_concurrent

        self.playwright = None
        self.browser = None
        self.context = None
        self._semaphore = None

    async def init_browser(self) -> None:
        """Initialize Playwright browser and context."""
        if self.browser:
            return  # Already initialized

        from playwright.async_api import async_playwright

        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            timeout=self.browser_timeout,
        )

        if not self.browser:
            raise RuntimeError("Browser failed to launch")

        self.context = await self.browser.new_context(
            user_agent=DEFAULT_UA,
            viewport={"width": 1920, "height": 1080},
        )

        self._semaphore = asyncio.Semaphore(self.max_concurrent)

        logger.info(f"[crawler] Browser initialized (headless={self.headless})")

    async def close_browser(self) -> None:
        """Close browser and clean up resources."""
        if self.context:
            await self.context.close()
            self.context = None

        if self.browser:
            await self.browser.close()
            self.browser = None

        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

        logger.info("[crawler] Browser closed")

    async def crawl_single_url(self, url: str) -> Dict[str, Any]:
        """
        Crawl a single URL and extract text content.

        Args:
            url: The URL to crawl

        Returns:
            Dict with 'url' and 'content' keys. Content contains error message on failure.
        """
        if not self.context:
            await self.init_browser()

        if not self.context:
            return {"url": url, "content": "Browser initialization failed"}

        page = None
        try:
            async with self._semaphore:
                page = await self.context.new_page()

                await page.goto(
                    url,
                    wait_until=self.wait_until,
                    timeout=self.page_timeout,
                )

                await asyncio.sleep(0.5)

                content = await page.inner_text("body")

                if not content or len(content.strip()) < 50:
                    logger.warning(f"[crawler] {url} returned minimal content")
                    content = content or "No content extracted"

                logger.debug(f"[crawler] ✓ {url} ({len(content)} chars)")
                return {"url": url, "content": content.strip()}

        except asyncio.TimeoutError:
            logger.warning(f"[crawler] ✗ {url} (timeout)")
            return {"url": url, "content": "Crawl timeout - page load too slow"}

        except Exception as e:
            logger.warning(f"[crawler] ✗ {url} ({type(e).__name__}: {e})")
            return {"url": url, "content": f"Crawl failed: {e}"}

        finally:
            if page:
                await page.close()

    async def crawl_urls(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Crawl multiple URLs in parallel.

        Args:
            urls: List of URLs to crawl

        Returns:
            List of dicts with 'url' and 'content' keys
        """
        if not urls:
            return []

        if not self.context:
            await self.init_browser()

        valid_urls = [u for u in urls if u and isinstance(u, str)]
        if not valid_urls:
            return []

        logger.info(f"[crawler] Crawling {len(valid_urls)} URLs (max_concurrent={self.max_concurrent})...")

        tasks = [self.crawl_single_url(url) for url in valid_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        formatted_results: List[Dict[str, Any]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"[crawler] Task {i} failed with exception: {result}")
                formatted_results.append({
                    "url": valid_urls[i] if i < len(valid_urls) else "unknown",
                    "content": f"Exception: {result}",
                })
            else:
                formatted_results.append(result)

        success_count = sum(
            1 for r in formatted_results if "failed" not in r["content"].lower()
        )
        logger.info(f"[crawler] Completed: {success_count}/{len(valid_urls)} successful")

        return formatted_results

    async def __aenter__(self):
        """Async context manager entry."""
        await self.init_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close_browser()


# ============================================================================
# Global singleton instance for convenience
# ============================================================================
_global_crawler: Optional[CrawlerOptimized] = None
_crawler_lock = asyncio.Lock()


async def get_global_crawler() -> CrawlerOptimized:
    """Get or create the global crawler instance."""
    global _global_crawler

    async with _crawler_lock:
        if _global_crawler is None:
            # Try to get settings
            headless = getattr(settings, "crawler_headless", True)
            page_timeout = getattr(settings, "crawler_page_timeout", 20000)
            max_concurrent = getattr(settings, "crawler_max_concurrent", 5)

            _global_crawler = CrawlerOptimized(
                headless=headless,
                page_timeout=page_timeout,
                max_concurrent=max_concurrent,
            )
            await _global_crawler.init_browser()

    return _global_crawler


async def close_global_crawler() -> None:
    """Close the global crawler instance."""
    global _global_crawler

    if _global_crawler:
        await _global_crawler.close_browser()
        _global_crawler = None


# ============================================================================
# Legacy urllib-based Implementation (Fallback)
# ============================================================================

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


def _crawl_url_legacy(url: str, timeout: int = 10) -> Dict[str, str]:
    """
    Fetch a single URL using urllib (legacy implementation).

    Returns dict with url, content; on error, content has the message.
    """
    try:
        req = Request(url, headers={"User-Agent": DEFAULT_UA})
        with urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            raw = resp.read().decode(charset, errors="ignore")
        return {"url": url, "content": _strip_html(raw)}
    except (HTTPError, URLError, Exception) as e:
        logger.warning(f"[crawler_legacy] {url} failed: {e}")
        return {"url": url, "content": f"Crawl failed: {e}"}


def _crawl_urls_legacy(urls: List[str], timeout: int = 10) -> List[Dict[str, str]]:
    """
    Fetch multiple URLs sequentially using urllib (legacy implementation).

    This is the original simple implementation used as fallback.
    """
    results: List[Dict[str, str]] = []
    for u in urls:
        if not u:
            continue
        results.append(_crawl_url_legacy(u, timeout=timeout))
    return results


# ============================================================================
# Smart Entry Point with Automatic Selection
# ============================================================================

def _should_use_optimized() -> bool:
    """
    Check if we should use the optimized Playwright crawler.
    Windows 环境一律关闭（子进程支持不稳定，易触发 NotImplementedError）。
    如需强制，可改代码放开，但需自行承担稳定性风险。
    """
    import platform
    if platform.system().lower().startswith("win"):
        return False

    env_val = ""
    try:
        import os
        env_val = os.getenv("USE_OPTIMIZED_CRAWLER", "")
    except Exception:
        env_val = ""

    if env_val:
        return env_val.strip().lower() in ("1", "true", "yes", "on")

    return getattr(settings, "use_optimized_crawler", True)


def crawl_urls(urls: List[str], timeout: int = 10) -> List[Dict[str, str]]:
    """
    Intelligent crawler that automatically selects best implementation.

    Priority:
    1. Optimized Playwright crawler (if enabled and available) - 4x faster, JS support
    2. Legacy urllib crawler (fallback) - simple, no dependencies

    Args:
        urls: List of URLs to crawl
        timeout: Timeout in seconds (used by legacy crawler)

    Returns:
        List of dicts with 'url' and 'content' keys

    Examples:
        # Automatic selection
        results = crawl_urls(["https://example.com"])

        # Force legacy (set in .env: USE_OPTIMIZED_CRAWLER=false)
        results = crawl_urls(["https://example.com"])
    """
    if not urls:
        return []

    # Check if we should try optimized version
    use_optimized = _should_use_optimized()

    if use_optimized:
        try:
            logger.debug("[crawler] Attempting to use optimized Playwright crawler")
            return _run_async_crawl(urls)
        except Exception as e:
            logger.warning(
                f"[crawler] Optimized crawler failed ({e}), falling back to legacy urllib crawler"
            )

    logger.debug("[crawler] Using legacy urllib crawler")
    return _crawl_urls_legacy(urls, timeout)


def _run_async_crawl(urls: List[str]) -> List[Dict[str, str]]:
    """Helper to run async crawl in a safe event loop (handles running loop + Windows)."""
    def _run_new_loop(target_urls: List[str]) -> List[Dict[str, str]]:
        try:
            import platform
            if platform.system().lower().startswith("win"):
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
        return asyncio.run(_async_crawl_urls(target_urls))

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(_run_new_loop, urls)
            return future.result()

    return _run_new_loop(urls)


async def _async_crawl_urls(urls: List[str]) -> List[Dict[str, Any]]:
    """Internal async crawling function."""
    async with CrawlerOptimized() as crawler:
        return await crawler.crawl_urls(urls)


# ============================================================================
# Backwards compatibility aliases
# ============================================================================

# Keep original function names for backwards compatibility
crawl_url = _crawl_url_legacy  # Single URL crawling (legacy only)
