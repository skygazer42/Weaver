"""
Lightweight in-memory search cache and query deduplicator.

Used by web_plan and deepsearch flows to avoid repeat searches in a single
process. No persistence; safe for multi-threaded asyncio because operations
are simple and fast.
"""

from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Tuple


class SearchCache:
    """Simple LRU cache for search results."""

    def __init__(self, max_items: int = 256):
        self.max_items = max_items
        self._data: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str):
        if key in self._data:
            value = self._data.pop(key)
            self._data[key] = value
            return value
        return None

    def set(self, key: str, value: Any) -> None:
        if key in self._data:
            self._data.pop(key)
        self._data[key] = value
        if len(self._data) > self.max_items:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()


class QueryDeduplicator:
    """
    Deduplicate similar queries.

    Current strategy: normalize to lowercase and strip spaces, then drop exact
    duplicates. Similarity threshold parameter kept for future use.
    """

    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold

    def deduplicate(self, queries: Iterable[str]) -> Tuple[List[str], List[str]]:
        seen = set()
        uniques: List[str] = []
        dupes: List[str] = []

        for q in queries:
            if not q:
                continue
            norm = " ".join(q.split()).lower()
            if norm in seen:
                dupes.append(q)
                continue
            seen.add(norm)
            uniques.append(q)
        return uniques, dupes


# Global process-local cache
_cache = SearchCache()


def get_search_cache() -> SearchCache:
    return _cache


__all__ = ["SearchCache", "QueryDeduplicator", "get_search_cache"]
