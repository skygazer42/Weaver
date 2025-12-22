"""
Search Cache - LRU cache for search results with TTL support.

Prevents redundant API calls for similar/duplicate queries within a session.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached search result entry."""
    query: str
    results: List[Dict[str, Any]]
    timestamp: float
    hit_count: int = 0


class SearchCache:
    """
    Thread-safe LRU cache for search results.

    Features:
    - TTL-based expiration
    - Semantic similarity matching (finds similar queries)
    - LRU eviction when capacity reached
    - Thread-safe operations
    """

    def __init__(
        self,
        max_size: int = 100,
        ttl_seconds: float = 3600,  # 1 hour default
        similarity_threshold: float = 0.85,
    ):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.similarity_threshold = similarity_threshold
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()

        # Stats
        self.hits = 0
        self.misses = 0
        self.similar_hits = 0

    def _normalize_query(self, query: str) -> str:
        """Normalize query for consistent caching."""
        return " ".join(query.lower().split())

    def _query_hash(self, query: str) -> str:
        """Generate hash for exact matching."""
        normalized = self._normalize_query(query)
        return hashlib.md5(normalized.encode()).hexdigest()[:16]

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if entry has expired."""
        return (time.time() - entry.timestamp) > self.ttl_seconds

    def _find_similar(self, query: str) -> Optional[CacheEntry]:
        """Find a similar query in cache using fuzzy matching."""
        normalized = self._normalize_query(query)

        for key, entry in self._cache.items():
            if self._is_expired(entry):
                continue

            cached_normalized = self._normalize_query(entry.query)
            similarity = SequenceMatcher(None, normalized, cached_normalized).ratio()

            if similarity >= self.similarity_threshold:
                return entry

        return None

    def get(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached results for a query.

        Checks exact match first, then similar queries.

        Returns:
            Cached results if found and not expired, None otherwise
        """
        with self._lock:
            query_hash = self._query_hash(query)

            # Try exact match first
            if query_hash in self._cache:
                entry = self._cache[query_hash]
                if not self._is_expired(entry):
                    # Move to end (most recently used)
                    self._cache.move_to_end(query_hash)
                    entry.hit_count += 1
                    self.hits += 1
                    logger.debug(f"[search_cache] Exact hit for: {query[:50]}")
                    return entry.results
                else:
                    # Remove expired entry
                    del self._cache[query_hash]

            # Try similar query match
            similar_entry = self._find_similar(query)
            if similar_entry:
                similar_entry.hit_count += 1
                self.similar_hits += 1
                logger.debug(f"[search_cache] Similar hit for: {query[:50]}")
                return similar_entry.results

            self.misses += 1
            return None

    def set(self, query: str, results: List[Dict[str, Any]]) -> None:
        """Cache search results for a query."""
        with self._lock:
            query_hash = self._query_hash(query)

            # Evict oldest if at capacity
            while len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)

            self._cache[query_hash] = CacheEntry(
                query=query,
                results=results,
                timestamp=time.time(),
            )

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0
            self.similar_hits = 0

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of removed entries."""
        with self._lock:
            expired_keys = [
                k for k, v in self._cache.items()
                if self._is_expired(v)
            ]
            for k in expired_keys:
                del self._cache[k]
            return len(expired_keys)

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self.hits + self.similar_hits + self.misses
            hit_rate = (self.hits + self.similar_hits) / max(total_requests, 1)

            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self.hits,
                "similar_hits": self.similar_hits,
                "misses": self.misses,
                "hit_rate": round(hit_rate, 3),
            }


# Global cache instance
_search_cache: Optional[SearchCache] = None


def get_search_cache() -> SearchCache:
    """Get the global search cache instance."""
    global _search_cache
    if _search_cache is None:
        _search_cache = SearchCache()
    return _search_cache


def clear_search_cache() -> None:
    """Clear the global search cache."""
    global _search_cache
    if _search_cache:
        _search_cache.clear()


class QueryDeduplicator:
    """
    Deduplicates queries before execution.

    Prevents sending duplicate or near-duplicate queries to the search API.
    """

    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold

    def _normalize(self, query: str) -> str:
        """Normalize query for comparison."""
        return " ".join(query.lower().split())

    def deduplicate(self, queries: List[str]) -> Tuple[List[str], List[str]]:
        """
        Deduplicate a list of queries.

        Returns:
            (unique_queries, duplicate_queries)
        """
        if not queries:
            return [], []

        unique: List[str] = []
        duplicates: List[str] = []
        seen_normalized: List[str] = []

        for query in queries:
            normalized = self._normalize(query)

            # Check if similar to any seen query
            is_duplicate = False
            for seen in seen_normalized:
                similarity = SequenceMatcher(None, normalized, seen).ratio()
                if similarity >= self.similarity_threshold:
                    is_duplicate = True
                    break

            if is_duplicate:
                duplicates.append(query)
            else:
                unique.append(query)
                seen_normalized.append(normalized)

        if duplicates:
            logger.info(f"[query_dedup] Removed {len(duplicates)} duplicate queries")

        return unique, duplicates
