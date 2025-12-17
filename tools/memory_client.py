import json
import logging
from typing import List, Optional
from pathlib import Path

from common.config import settings

logger = logging.getLogger(__name__)

_mem_client = None
_fallback_path = Path(".memory_store.json")


def _get_mem_client():
    """Lazy-load mem0 client if available and enabled."""
    global _mem_client
    if not settings.enable_memory:
        return None
    if _mem_client is not None:
        return _mem_client
    try:
        from mem0 import Memory
    except Exception:
        logger.warning("mem0 not installed; memory disabled.")
        return None

    try:
        _mem_client = Memory(api_key=settings.mem0_api_key or None)
        return _mem_client
    except Exception as e:
        logger.warning(f"Failed to init mem0 client: {e}")
        return None


def _fallback_load() -> dict:
    if not _fallback_path.exists():
        return {}
    try:
        return json.loads(_fallback_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _fallback_save(data: dict) -> None:
    try:
        _fallback_path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to write fallback memory store: {e}")


def add_memory_entry(content: str, user_id: Optional[str] = None) -> bool:
    """Store a memory entry (long-term)."""
    user = user_id or settings.memory_user_id
    if not content:
        return False

    client = _get_mem_client()
    if client:
        try:
            client.add(content, user_id=user, namespace=settings.memory_namespace)
            return True
        except Exception as e:
            logger.warning(f"mem0 add failed: {e}")

    # Fallback to local JSON store
    data = _fallback_load()
    entries = data.get(user, [])
    entries.append(content)
    # Trim to max entries
    max_entries = max(1, int(settings.memory_max_entries or 20))
    entries = entries[-max_entries:]
    data[user] = entries
    _fallback_save(data)
    return True


def store_interaction(user_input: str, assistant_output: str, user_id: Optional[str] = None) -> bool:
    """Store a combined interaction for better recall."""
    combined = f"User: {user_input}\nAssistant: {assistant_output}"
    return add_memory_entry(combined, user_id=user_id)


def fetch_memories(query: str = "*", user_id: Optional[str] = None, limit: Optional[int] = None) -> List[str]:
    """Retrieve memories (most recent first)."""
    user = user_id or settings.memory_user_id
    k = limit or settings.memory_top_k

    client = _get_mem_client()
    if client:
        try:
            results = client.search(
                query=query or "*",
                user_id=user,
                namespace=settings.memory_namespace,
                top_k=k
            )
            # mem0 returns list of dicts with "content" key
            if isinstance(results, list):
                out = []
                for item in results:
                    if isinstance(item, dict) and item.get("content"):
                        out.append(str(item["content"]))
                    elif isinstance(item, str):
                        out.append(item)
                return out[:k]
        except Exception as e:
            logger.warning(f"mem0 search failed: {e}")

    # Fallback to local JSON store (no semantic search, just recent)
    data = _fallback_load()
    entries = data.get(user, [])
    return list(reversed(entries))[:k]
