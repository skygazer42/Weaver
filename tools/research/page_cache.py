from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from common.config import settings
from tools.research.models import FetchedPage


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    expires_at: float
    payload: dict


class FetchedPageCache:
    def __init__(self, *, max_entries: int, ttl_s: float) -> None:
        self.max_entries = max(1, int(max_entries))
        self.ttl_s = float(ttl_s)
        self._lock = threading.RLock()
        self._data: OrderedDict[str, _CacheEntry] = OrderedDict()

    def get(self, key: str) -> Optional[FetchedPage]:
        if not key:
            return None

        now = time.time()
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            if entry.expires_at <= now:
                self._data.pop(key, None)
                return None

            # LRU bump.
            self._data.move_to_end(key)
            try:
                return FetchedPage(**dict(entry.payload))
            except Exception:
                return None

    def set(self, key: str, page: FetchedPage) -> None:
        if not key:
            return

        expires_at = time.time() + max(0.0, float(self.ttl_s))
        payload = page.to_dict()

        with self._lock:
            self._data[key] = _CacheEntry(expires_at=expires_at, payload=payload)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_cache: Optional[FetchedPageCache] = None
_cache_lock = threading.RLock()


def get_fetched_page_cache() -> Optional[FetchedPageCache]:
    ttl_s = float(getattr(settings, "research_fetch_cache_ttl_s", 0.0) or 0.0)
    max_entries = int(getattr(settings, "research_fetch_cache_max_entries", 0) or 0)

    if ttl_s <= 0.0 or max_entries <= 0:
        return None

    global _cache
    with _cache_lock:
        if _cache is None or _cache.ttl_s != ttl_s or _cache.max_entries != max_entries:
            _cache = FetchedPageCache(max_entries=max_entries, ttl_s=ttl_s)
        return _cache


def clear_fetched_page_cache() -> None:
    global _cache
    with _cache_lock:
        if _cache is not None:
            _cache.clear()
        _cache = None

