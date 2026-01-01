import json
import logging
from typing import Any, List, Optional
from pathlib import Path

from common.config import settings

logger = logging.getLogger(__name__)

_MEM_INIT_FAILED = object()
_mem_client: Any = None
_ROOT_DIR = Path(__file__).resolve().parents[1]
_fallback_path = _ROOT_DIR / "data" / "memory_store.json"
_legacy_fallback_path = _ROOT_DIR / ".memory_store.json"


def _ensure_fallback_path():
    """
    Ensure fallback path exists under `data/` and migrate legacy root file if present.
    """
    if _fallback_path.exists():
        return
    if not _legacy_fallback_path.exists():
        return
    try:
        _fallback_path.parent.mkdir(parents=True, exist_ok=True)
        _legacy_fallback_path.replace(_fallback_path)
        logger.info("Migrated legacy memory store to %s", _fallback_path)
    except Exception as e:
        # Best-effort: keep working by reading legacy path when needed
        logger.warning("Failed to migrate legacy memory store: %s", e)


def _get_mem_client():
    """Lazy-load mem0 client if available and enabled."""
    global _mem_client
    if not settings.enable_memory:
        return None
    if _mem_client is _MEM_INIT_FAILED:
        return None
    if _mem_client is not None:
        return _mem_client

    try:
        import mem0  # noqa: F401
    except Exception:
        logger.warning("mem0 not installed; memory disabled.")
        _mem_client = _MEM_INIT_FAILED
        return None

    # mem0ai>=1.0.0 exposes a hosted API client via MemoryClient; prefer that.
    try:
        from mem0 import MemoryClient  # type: ignore
    except Exception:
        MemoryClient = None  # type: ignore

    if MemoryClient is not None:
        try:
            _mem_client = MemoryClient(api_key=settings.mem0_api_key or None)
            return _mem_client
        except Exception as e:
            logger.warning(f"Failed to init mem0 MemoryClient: {e}")
            _mem_client = _MEM_INIT_FAILED
            return None

    # Backward-compatible fallback for older mem0 versions.
    try:
        from mem0 import Memory  # type: ignore
        _mem_client = Memory(api_key=settings.mem0_api_key or None)
        return _mem_client
    except Exception as e:
        logger.warning(f"Failed to init mem0 client: {e}")
        _mem_client = _MEM_INIT_FAILED
        return None


def _fallback_load() -> dict:
    _ensure_fallback_path()
    # Prefer new location; fall back to legacy root file if migration failed.
    path = _fallback_path if _fallback_path.exists() else _legacy_fallback_path
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _fallback_save(data: dict) -> None:
    try:
        _fallback_path.parent.mkdir(parents=True, exist_ok=True)
        _fallback_path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
        # Clean up legacy file if it still exists after successful write
        if _legacy_fallback_path.exists():
            try:
                _legacy_fallback_path.unlink()
            except Exception:
                pass
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
            client.add(content, user_id=user)
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
            # mem0 MemoryClient uses `top_k`; older clients may accept `limit`.
            try:
                results = client.search(query=query or "*", user_id=user, top_k=k)
            except TypeError:
                results = client.search(query=query or "*", user_id=user, limit=k)

            # Normalize common return shapes across mem0 versions:
            # - list[dict|str]
            # - {"results": [...]}
            if isinstance(results, dict):
                results = results.get("results", [])

            out: List[str] = []
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, str) and item.strip():
                        out.append(item.strip())
                        continue
                    if not isinstance(item, dict):
                        continue
                    # Try a few common keys used across mem0 API versions.
                    for key in ("content", "text", "memory", "message"):
                        val = item.get(key)
                        if isinstance(val, str) and val.strip():
                            out.append(val.strip())
                            break
                    else:
                        # Sometimes the payload nests under "memory" or "data".
                        nested = item.get("memory") if isinstance(item.get("memory"), dict) else item.get("data")
                        if isinstance(nested, dict):
                            for key in ("content", "text"):
                                val = nested.get(key)
                                if isinstance(val, str) and val.strip():
                                    out.append(val.strip())
                                    break

            if out:
                return out[:k]
        except Exception as e:
            logger.warning(f"mem0 search failed: {e}")

    # Fallback to local JSON store (no semantic search, just recent)
    data = _fallback_load()
    entries = data.get(user, [])
    return list(reversed(entries))[:k]
