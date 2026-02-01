import logging
import textwrap
from typing import List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from agent.core.llm_factory import create_summary_model
from common.config import settings

logger = logging.getLogger(__name__)

# Use shared factory
_chat_model_summary = create_summary_model


def _messages_to_text(messages: List[BaseMessage]) -> str:
    lines = []
    for m in messages:
        role = m.type if hasattr(m, "type") else m.__class__.__name__
        content = getattr(m, "content", "")
        if isinstance(content, list):
            # for multimodal, keep text parts only
            text_parts = [p.get("text", "") for p in content if isinstance(p, dict)]
            content = "\n".join(text_parts)
        lines.append(f"[{role}] {content}")
    return "\n".join(lines)


def summarize_messages(messages: List[BaseMessage]) -> SystemMessage:
    """Summarize middle conversation history into a compact system message."""
    if not messages:
        return SystemMessage(content="Conversation summary: (empty)")

    llm = _chat_model_summary()
    word_limit = int(settings.summary_messages_word_limit or 200)
    prompt = textwrap.dedent(
        f"""You are a concise summarizer.
Keep critical facts, names, numbers, decisions, and user intent.
Do NOT add new info. Respond in <= {word_limit} words.

Conversation:
{{conversation}}
"""
    )
    convo_text = _messages_to_text(messages)
    try:
        resp = llm.invoke([HumanMessage(content=prompt.format(conversation=convo_text))])
        content = getattr(resp, "content", "") or convo_text[:500]
    except Exception as e:
        logger.warning(f"Summarization failed, falling back to truncation: {e}")
        content = convo_text[:500]

    return SystemMessage(content=f"Conversation summary:\\n{content.strip()}")
