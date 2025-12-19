import time
import logging
from typing import Any, Callable, Dict, List

from langchain_core.messages import BaseMessage, ToolMessage

from common.config import settings

logger = logging.getLogger(__name__)


def retry_call(fn: Callable, *, attempts: int, backoff: float, **kwargs) -> Any:
    """
    Simple synchronous retry helper with exponential backoff.
    """
    last_exc = None
    for i in range(attempts):
        try:
            return fn(**kwargs)
        except Exception as e:
            last_exc = e
            wait = backoff * (2 ** i)
            logger.warning(f"Tool call failed (attempt {i+1}/{attempts}): {e}; retrying in {wait:.1f}s")
            time.sleep(wait)
    if last_exc:
        raise last_exc
    return None


def enforce_tool_call_limit(state: Dict[str, Any], limit: int) -> None:
    """
    Increment and enforce per-run tool call limit stored on state.
    limit=0 means unlimited.
    """
    if limit <= 0:
        return
    count = int(state.get("tool_call_count", 0)) + 1
    state["tool_call_count"] = count
    if count > limit:
        raise RuntimeError(f"Tool call limit exceeded ({count}/{limit})")


def maybe_strip_tool_messages(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Optionally remove ToolMessage from history to save tokens.
    """
    if not settings.strip_tool_messages:
        return messages
    return [m for m in messages if not isinstance(m, ToolMessage)]

