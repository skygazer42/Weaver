"""
Stuck detection middleware: detects repeated assistant messages and injects a nudge.
"""

from typing import List

from langchain_core.messages import AIMessage, BaseMessage


def detect_stuck(messages: List[BaseMessage], threshold: int = 2) -> bool:
    if len(messages) < threshold + 1:
        return False
    last = messages[-1]
    if not isinstance(last, AIMessage) or not last.content:
        return False
    dup = 0
    for m in reversed(messages[:-1]):
        if isinstance(m, AIMessage) and m.content == last.content:
            dup += 1
        else:
            break
    return dup >= threshold


def inject_stuck_hint(messages: List[BaseMessage]) -> List[BaseMessage]:
    hint = AIMessage(content="Detected repeated answers. Please try a different approach or use other tools.")
    return messages + [hint]
