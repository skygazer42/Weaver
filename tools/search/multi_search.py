"""
Multi-Search Engine Aggregation.

Inspired by DeerFlow's multi-provider search approach.
Implements robust multi-provider search with intelligent result aggregation.

Key Features:
1. Multiple search provider adapters (Tavily, DuckDuckGo, Brave, Serper, Exa)
2. Intelligent result aggregation and deduplication
3. Provider health monitoring and automatic failover
4. Quality scoring per provider based on historical accuracy
"""

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from common.config import settings

logger = logging.getLogger(__name__)


class SearchStrategy(str, Enum):
    """Search execution strategy."""
    FALLBACK = "fallback"  # Try providers sequentially until success
    PARALLEL = "parallel"  # Query all providers in parallel, merge results
    ROUND_ROBIN = "round_robin"  # Distribute queries across providers
    BEST_FIRST = "best_first"  # Use best performing provider first


@dataclass
class SearchResult:
    """Normalized search result from any provider."""
    title: str
    url: str
    snippet: str
    content: str = ""
    score: float = 0.0
    published_date: Optional[str] = None
    provider: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def domain(self) -> str:
        """Extract domain from URL."""
        try:
            return urlparse(self.url).netloc
        except Exception:
            return ""

    @property
    def url_hash(self) -> str:
        """Get hash of URL for deduplication."""
        return hashlib.md5(self.url.encode()).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "content": self.content,
            "score": self.score,
            "published_date": self.published_date,
            "provider": self.provider,
        }


@dataclass
class ProviderStats:
    """Track provider performance statistics."""
    name: str
    total_calls: int = 0
    success_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0
    avg_result_quality: float = 0.5
    last_error: Optional[str] = None
    last_error_time: Optional[str] = None
    is_healthy: bool = True
    consecutive_failures: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.success_count / self.total_calls

    @property
    def avg_latency_ms(self) -> float:
        if self.success_count == 0:
            return 0
        return self.total_latency_ms / self.success_count

    def record_success(self, latency_ms: float, quality: float = 0.5) -> None:
        self.total_calls += 1
        self.success_count += 1
        self.total_latency_ms += latency_ms
        self.avg_result_quality = (self.avg_result_quality * 0.9) + (quality * 0.1)
        self.consecutive_failures = 0
        self.is_healthy = True

    def record_failure(self, error: str) -> None:
        self.total_calls += 1
        self.error_count += 1
        self.last_error = error
        self.last_error_time = datetime.now().isoformat()
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            self.is_healthy = False


class SearchProvider(ABC):
    """Abstract base class for search providers."""

    def __init__(self, name: str, api_key: Optional[str] = None):
        self.name = name
        self.api_key = api_key
        self.stats = ProviderStats(name=name)

    @abstractmethod
    def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """Execute a search query and return normalized results."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available (API key configured, etc.)."""
        pass

    def get_stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "success_rate": self.stats.success_rate,
            "avg_latency_ms": self.stats.avg_latency_ms,
            "avg_result_quality": self.stats.avg_result_quality,
            "is_healthy": self.stats.is_healthy,
        }


class TavilyProvider(SearchProvider):
    """Tavily search provider (primary)."""

    def __init__(self):
        super().__init__("tavily", settings.tavily_api_key)

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        from tools.search.search import tavily_search

        start_time = time.time()
        try:
            raw_results = tavily_search.invoke({
                "query": query,
                "max_results": max_results,
            })

            results = []
            for r in raw_results:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("summary", r.get("snippet", "")),
                    content=r.get("raw_excerpt", ""),
                    score=float(r.get("score", 0.5)),
                    published_date=r.get("published_date"),
                    provider=self.name,
                    raw_data=r,
                ))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.8)
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[TavilyProvider] Search failed: {e}")
            return []


class DuckDuckGoProvider(SearchProvider):
    """DuckDuckGo search provider (no API key required)."""

    def __init__(self):
        super().__init__("duckduckgo")

    def is_available(self) -> bool:
        try:
            from duckduckgo_search import DDGS
            return True
        except ImportError:
            return False

    def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.warning("[DuckDuckGoProvider] duckduckgo_search not installed")
            return []

        start_time = time.time()
        try:
            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=max_results))

            results = []
            for r in raw_results:
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", r.get("link", "")),
                    snippet=r.get("body", r.get("snippet", "")),
                    content="",
                    score=0.5,  # DDG doesn't provide scores
                    provider=self.name,
                    raw_data=r,
                ))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.6)
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[DuckDuckGoProvider] Search failed: {e}")
            return []


class BraveProvider(SearchProvider):
    """Brave Search provider."""

    def __init__(self):
        api_key = getattr(settings, "brave_api_key", None)
        super().__init__("brave", api_key)

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        import requests

        start_time = time.time()
        try:
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
            }
            params = {
                "q": query,
                "count": max_results,
            }
            response = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for r in data.get("web", {}).get("results", []):
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("description", ""),
                    content="",
                    score=0.6,
                    provider=self.name,
                    raw_data=r,
                ))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.7)
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[BraveProvider] Search failed: {e}")
            return []


class SerperProvider(SearchProvider):
    """Serper.dev Google Search provider."""

    def __init__(self):
        api_key = getattr(settings, "serper_api_key", None)
        super().__init__("serper", api_key)

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        import requests

        start_time = time.time()
        try:
            headers = {
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json",
            }
            payload = {
                "q": query,
                "num": max_results,
            }
            response = requests.post(
                "https://google.serper.dev/search",
                headers=headers,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for r in data.get("organic", []):
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("link", ""),
                    snippet=r.get("snippet", ""),
                    content="",
                    score=0.7,
                    published_date=r.get("date"),
                    provider=self.name,
                    raw_data=r,
                ))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.8)
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[SerperProvider] Search failed: {e}")
            return []


class ExaProvider(SearchProvider):
    """Exa.ai neural search provider."""

    def __init__(self):
        api_key = getattr(settings, "exa_api_key", None)
        super().__init__("exa", api_key)

    def is_available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        try:
            from exa_py import Exa
        except ImportError:
            logger.warning("[ExaProvider] exa_py not installed")
            return []

        start_time = time.time()
        try:
            exa = Exa(self.api_key)
            response = exa.search_and_contents(
                query,
                type="neural",
                num_results=max_results,
                text=True,
            )

            results = []
            for r in response.results:
                results.append(SearchResult(
                    title=r.title or "",
                    url=r.url or "",
                    snippet=r.text[:500] if r.text else "",
                    content=r.text or "",
                    score=r.score if hasattr(r, "score") else 0.7,
                    published_date=r.published_date if hasattr(r, "published_date") else None,
                    provider=self.name,
                    raw_data={"id": r.id},
                ))

            latency = (time.time() - start_time) * 1000
            self.stats.record_success(latency, 0.85)
            return results

        except Exception as e:
            self.stats.record_failure(str(e))
            logger.error(f"[ExaProvider] Search failed: {e}")
            return []


# Import feed providers (lazy to avoid circular imports)
def _get_feed_providers() -> List[SearchProvider]:
    """Get available real-time feed providers."""
    providers = []
    try:
        from tools.search.feeds.hackernews_provider import HackerNewsProvider
        hn = HackerNewsProvider()
        if hn.is_available():
            providers.append(hn)
    except ImportError:
        pass

    try:
        from tools.search.feeds.twitter_provider import TwitterProvider
        twitter = TwitterProvider()
        if twitter.is_available():
            providers.append(twitter)
    except ImportError:
        pass

    try:
        from tools.search.feeds.reddit_provider import RedditProvider
        reddit = RedditProvider()
        if reddit.is_available():
            providers.append(reddit)
    except ImportError:
        pass

    return providers


# Import academic providers (lazy to avoid circular imports)
def _get_academic_providers() -> List[SearchProvider]:
    """Get available academic search providers."""
    providers = []
    try:
        from tools.search.academic.arxiv_provider import ArxivProvider
        arxiv = ArxivProvider()
        if arxiv.is_available():
            providers.append(arxiv)
    except ImportError:
        pass

    try:
        from tools.search.academic.semantic_scholar_provider import SemanticScholarProvider
        ss = SemanticScholarProvider()
        if ss.is_available():
            providers.append(ss)
    except ImportError:
        pass

    try:
        from tools.search.academic.pubmed_provider import PubMedProvider
        pm = PubMedProvider()
        if pm.is_available():
            providers.append(pm)
    except ImportError:
        pass

    return providers


class MultiSearchOrchestrator:
    """
    Orchestrates searches across multiple providers.

    Supports multiple strategies:
    - FALLBACK: Try providers sequentially until success
    - PARALLEL: Query all providers in parallel, merge results
    - ROUND_ROBIN: Distribute queries across providers
    - BEST_FIRST: Use best performing provider first
    """

    def __init__(
        self,
        providers: Optional[List[SearchProvider]] = None,
        strategy: SearchStrategy = SearchStrategy.FALLBACK,
        similarity_threshold: float = 0.7,
    ):
        """
        Initialize the orchestrator.

        Args:
            providers: List of search providers to use
            strategy: Search execution strategy
            similarity_threshold: Threshold for content similarity deduplication
        """
        self.providers = providers or self._init_default_providers()
        self.strategy = strategy
        self.similarity_threshold = similarity_threshold
        self._round_robin_index = 0

    def _init_default_providers(self) -> List[SearchProvider]:
        """Initialize default providers based on available API keys."""
        providers = []

        # Tavily (primary)
        tavily = TavilyProvider()
        if tavily.is_available():
            providers.append(tavily)

        # DuckDuckGo (fallback, no API key needed)
        ddg = DuckDuckGoProvider()
        if ddg.is_available():
            providers.append(ddg)

        # Brave
        brave = BraveProvider()
        if brave.is_available():
            providers.append(brave)

        # Serper
        serper = SerperProvider()
        if serper.is_available():
            providers.append(serper)

        # Exa
        exa = ExaProvider()
        if exa.is_available():
            providers.append(exa)

        # Real-time feed providers
        feed_providers = _get_feed_providers()
        providers.extend(feed_providers)

        # Academic providers
        academic_providers = _get_academic_providers()
        providers.extend(academic_providers)

        logger.info(f"[MultiSearch] Initialized {len(providers)} providers: {[p.name for p in providers]}")
        return providers
        return providers

    def get_available_providers(self) -> List[SearchProvider]:
        """Get list of currently healthy and available providers."""
        return [p for p in self.providers if p.is_available() and p.stats.is_healthy]

    def search(
        self,
        query: str,
        max_results: int = 10,
        strategy: Optional[SearchStrategy] = None,
    ) -> List[SearchResult]:
        """
        Execute a search using the configured strategy.

        Args:
            query: Search query
            max_results: Maximum number of results
            strategy: Override the default strategy

        Returns:
            List of deduplicated search results
        """
        strategy = strategy or self.strategy
        available = self.get_available_providers()

        if not available:
            logger.error("[MultiSearch] No available search providers")
            return []

        if strategy == SearchStrategy.FALLBACK:
            return self._search_fallback(query, max_results, available)
        elif strategy == SearchStrategy.PARALLEL:
            return self._search_parallel(query, max_results, available)
        elif strategy == SearchStrategy.ROUND_ROBIN:
            return self._search_round_robin(query, max_results, available)
        elif strategy == SearchStrategy.BEST_FIRST:
            return self._search_best_first(query, max_results, available)
        else:
            return self._search_fallback(query, max_results, available)

    def _search_fallback(
        self,
        query: str,
        max_results: int,
        providers: List[SearchProvider],
    ) -> List[SearchResult]:
        """Try providers sequentially until success."""
        for provider in providers:
            results = provider.search(query, max_results)
            if results:
                logger.info(f"[MultiSearch] Got {len(results)} results from {provider.name}")
                return results
            logger.warning(f"[MultiSearch] {provider.name} returned no results, trying next...")

        logger.warning("[MultiSearch] All providers failed")
        return []

    def _search_parallel(
        self,
        query: str,
        max_results: int,
        providers: List[SearchProvider],
    ) -> List[SearchResult]:
        """Query all providers in parallel and merge results."""
        import concurrent.futures

        all_results = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers)) as executor:
            futures = {
                executor.submit(p.search, query, max_results): p
                for p in providers
            }

            for future in concurrent.futures.as_completed(futures, timeout=30):
                provider = futures[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                    logger.info(f"[MultiSearch] {provider.name} returned {len(results)} results")
                except Exception as e:
                    logger.error(f"[MultiSearch] {provider.name} failed: {e}")

        # Deduplicate and rank
        return self._deduplicate_and_rank(all_results, max_results)

    def _search_round_robin(
        self,
        query: str,
        max_results: int,
        providers: List[SearchProvider],
    ) -> List[SearchResult]:
        """Use round-robin to distribute queries."""
        if not providers:
            return []

        provider = providers[self._round_robin_index % len(providers)]
        self._round_robin_index += 1

        results = provider.search(query, max_results)
        if results:
            return results

        # Fallback to next provider if current fails
        return self._search_fallback(query, max_results, providers)

    def _search_best_first(
        self,
        query: str,
        max_results: int,
        providers: List[SearchProvider],
    ) -> List[SearchResult]:
        """Use best performing provider first."""
        # Sort by composite score: success_rate * quality / latency
        sorted_providers = sorted(
            providers,
            key=lambda p: (
                p.stats.success_rate *
                p.stats.avg_result_quality *
                (1000 / max(p.stats.avg_latency_ms, 100))
            ),
            reverse=True,
        )

        return self._search_fallback(query, max_results, sorted_providers)

    def _deduplicate_and_rank(
        self,
        results: List[SearchResult],
        max_results: int,
    ) -> List[SearchResult]:
        """Deduplicate results by URL and content similarity, then rank."""
        if not results:
            return []

        # URL-based deduplication
        seen_urls = set()
        unique = []

        for r in results:
            if r.url_hash not in seen_urls:
                seen_urls.add(r.url_hash)
                unique.append(r)

        # Content similarity deduplication
        if len(unique) > max_results:
            final = []
            for r in unique:
                is_duplicate = False
                for existing in final:
                    similarity = SequenceMatcher(
                        None,
                        r.snippet[:200].lower(),
                        existing.snippet[:200].lower(),
                    ).ratio()
                    if similarity > self.similarity_threshold:
                        is_duplicate = True
                        # Keep higher scored result
                        if r.score > existing.score:
                            final.remove(existing)
                            final.append(r)
                        break

                if not is_duplicate:
                    final.append(r)

                if len(final) >= max_results:
                    break

            unique = final

        # Rank by score
        unique.sort(key=lambda r: r.score, reverse=True)

        return unique[:max_results]

    def get_provider_stats(self) -> List[Dict[str, Any]]:
        """Get statistics for all providers."""
        return [p.get_stats() for p in self.providers]

    def reset_provider_health(self) -> None:
        """Reset health status for all providers."""
        for provider in self.providers:
            provider.stats.is_healthy = True
            provider.stats.consecutive_failures = 0


# Global orchestrator instance
_global_orchestrator: Optional[MultiSearchOrchestrator] = None


def get_search_orchestrator() -> MultiSearchOrchestrator:
    """Get or create the global search orchestrator."""
    global _global_orchestrator
    if _global_orchestrator is None:
        _global_orchestrator = MultiSearchOrchestrator()
    return _global_orchestrator


def multi_search(
    query: str,
    max_results: int = 10,
    strategy: SearchStrategy = SearchStrategy.FALLBACK,
) -> List[Dict[str, Any]]:
    """
    Convenience function for multi-provider search.

    Args:
        query: Search query
        max_results: Maximum number of results
        strategy: Search strategy to use

    Returns:
        List of result dictionaries
    """
    orchestrator = get_search_orchestrator()
    results = orchestrator.search(query, max_results, strategy)
    return [r.to_dict() for r in results]
