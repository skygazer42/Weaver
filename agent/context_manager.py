"""
Context Manager for Agent Conversations.

This module provides context window management for AI agents, including:
- Token counting using tiktoken
- Message truncation strategies
- Important message preservation
- Dynamic context window optimization

Similar to Manus's context_manager.py but adapted for Weaver's LangChain architecture.

Usage:
    from agent.context_manager import ContextManager, get_context_manager

    manager = get_context_manager(model="gpt-4")
    truncated = manager.truncate_messages(messages, max_tokens=8000)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

logger = logging.getLogger(__name__)

# Try to import tiktoken for accurate token counting
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("[context_manager] tiktoken not installed. Using character-based estimation.")


# Model token limits (context window sizes)
MODEL_TOKEN_LIMITS = {
    # OpenAI models
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "gpt-4-turbo": 128000,
    "gpt-4-turbo-preview": 128000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-3.5-turbo": 16385,
    "gpt-3.5-turbo-16k": 16385,
    # Anthropic models
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "claude-3-5-sonnet": 200000,
    "claude-2": 100000,
    # Google models
    "gemini-pro": 32000,
    "gemini-1.5-pro": 1000000,
    "gemini-1.5-flash": 1000000,
    # Default
    "default": 8192,
}

# Encoding mappings for tiktoken
MODEL_ENCODINGS = {
    "gpt-4": "cl100k_base",
    "gpt-4-32k": "cl100k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-4-turbo-preview": "cl100k_base",
    "gpt-4o": "cl100k_base",
    "gpt-4o-mini": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "gpt-3.5-turbo-16k": "cl100k_base",
    "claude-3-opus": "cl100k_base",  # Use OpenAI encoding as approximation
    "claude-3-sonnet": "cl100k_base",
    "claude-3-haiku": "cl100k_base",
    "claude-3-5-sonnet": "cl100k_base",
    "claude-2": "cl100k_base",
    "gemini-pro": "cl100k_base",
    "gemini-1.5-pro": "cl100k_base",
    "gemini-1.5-flash": "cl100k_base",
    "default": "cl100k_base",
}


@dataclass
class TokenStats:
    """Statistics about token usage."""
    total_tokens: int = 0
    system_tokens: int = 0
    user_tokens: int = 0
    assistant_tokens: int = 0
    tool_tokens: int = 0
    message_count: int = 0
    truncated_count: int = 0


@dataclass
class TruncationConfig:
    """Configuration for message truncation."""
    # Maximum tokens for the context
    max_tokens: int = 8000
    # Reserve tokens for model response
    reserve_tokens: int = 1000
    # Always keep first N system messages
    keep_system_messages: int = 2
    # Always keep last N user messages
    keep_recent_messages: int = 4
    # Truncation strategy: "smart", "fifo", "middle"
    strategy: str = "smart"
    # Minimum tokens per message before removing entirely
    min_message_tokens: int = 50


class ContextManager:
    """
    Manages context window for LLM conversations.

    Features:
    - Accurate token counting using tiktoken
    - Multiple truncation strategies
    - System message preservation
    - Recent context priority
    """

    def __init__(
        self,
        model: str = "gpt-4",
        config: Optional[TruncationConfig] = None,
    ):
        self.model = self._normalize_model_name(model)
        self.config = config or TruncationConfig()
        self._encoder = self._get_encoder()

        # Get model token limit
        self.max_context_tokens = MODEL_TOKEN_LIMITS.get(
            self.model, MODEL_TOKEN_LIMITS["default"]
        )

    def _normalize_model_name(self, model: str) -> str:
        """Normalize model name for lookup."""
        model_lower = model.lower()

        # Map common variations
        if "gpt-4o" in model_lower:
            if "mini" in model_lower:
                return "gpt-4o-mini"
            return "gpt-4o"
        if "gpt-4-turbo" in model_lower or "gpt-4-1106" in model_lower:
            return "gpt-4-turbo"
        if "gpt-4-32k" in model_lower:
            return "gpt-4-32k"
        if "gpt-4" in model_lower:
            return "gpt-4"
        if "gpt-3.5" in model_lower:
            return "gpt-3.5-turbo"
        if "claude-3-5" in model_lower or "claude-3.5" in model_lower:
            return "claude-3-5-sonnet"
        if "claude-3" in model_lower:
            if "opus" in model_lower:
                return "claude-3-opus"
            if "haiku" in model_lower:
                return "claude-3-haiku"
            return "claude-3-sonnet"
        if "claude-2" in model_lower:
            return "claude-2"
        if "gemini-1.5" in model_lower:
            if "flash" in model_lower:
                return "gemini-1.5-flash"
            return "gemini-1.5-pro"
        if "gemini" in model_lower:
            return "gemini-pro"

        return model_lower

    def _get_encoder(self):
        """Get tiktoken encoder for the model."""
        if not TIKTOKEN_AVAILABLE:
            return None

        encoding_name = MODEL_ENCODINGS.get(self.model, MODEL_ENCODINGS["default"])
        try:
            return tiktoken.get_encoding(encoding_name)
        except Exception as e:
            logger.warning(f"[context_manager] Failed to get encoder: {e}")
            return None

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in a text string.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        if not text:
            return 0

        if self._encoder:
            try:
                return len(self._encoder.encode(text))
            except Exception:
                pass

        # Fallback: estimate ~4 characters per token
        return len(text) // 4

    def count_message_tokens(self, message: BaseMessage) -> int:
        """
        Count tokens in a single message.

        Args:
            message: LangChain message object

        Returns:
            Token count including role overhead
        """
        content = message.content if hasattr(message, "content") else str(message)

        # Base tokens for content
        tokens = self.count_tokens(content)

        # Add overhead for message structure (~4 tokens per message)
        tokens += 4

        # Add name overhead if present
        if hasattr(message, "name") and message.name:
            tokens += self.count_tokens(message.name) + 1

        return tokens

    def count_messages_tokens(self, messages: List[BaseMessage]) -> TokenStats:
        """
        Count tokens for a list of messages with detailed stats.

        Args:
            messages: List of LangChain messages

        Returns:
            TokenStats with detailed breakdown
        """
        stats = TokenStats(message_count=len(messages))

        for msg in messages:
            tokens = self.count_message_tokens(msg)
            stats.total_tokens += tokens

            if isinstance(msg, SystemMessage):
                stats.system_tokens += tokens
            elif isinstance(msg, HumanMessage):
                stats.user_tokens += tokens
            elif isinstance(msg, AIMessage):
                stats.assistant_tokens += tokens
            elif isinstance(msg, ToolMessage):
                stats.tool_tokens += tokens

        # Add final assistant response overhead
        stats.total_tokens += 3

        return stats

    def truncate_messages(
        self,
        messages: List[BaseMessage],
        max_tokens: Optional[int] = None,
        strategy: Optional[str] = None,
    ) -> Tuple[List[BaseMessage], TokenStats]:
        """
        Truncate messages to fit within token limit.

        Args:
            messages: List of messages to truncate
            max_tokens: Maximum tokens (uses config if not specified)
            strategy: Truncation strategy ("smart", "fifo", "middle")

        Returns:
            Tuple of (truncated messages, token stats)
        """
        max_tokens = max_tokens or self.config.max_tokens
        strategy = strategy or self.config.strategy

        # Reserve tokens for response
        available_tokens = max_tokens - self.config.reserve_tokens

        # Check if truncation needed
        stats = self.count_messages_tokens(messages)
        if stats.total_tokens <= available_tokens:
            return messages, stats

        logger.info(
            f"[context_manager] Truncating messages: {stats.total_tokens} -> {available_tokens} tokens"
        )

        if strategy == "smart":
            return self._truncate_smart(messages, available_tokens)
        elif strategy == "fifo":
            return self._truncate_fifo(messages, available_tokens)
        elif strategy == "middle":
            return self._truncate_middle(messages, available_tokens)
        else:
            return self._truncate_smart(messages, available_tokens)

    def _truncate_smart(
        self,
        messages: List[BaseMessage],
        max_tokens: int,
    ) -> Tuple[List[BaseMessage], TokenStats]:
        """
        Smart truncation: preserve system messages and recent context.

        Strategy:
        1. Always keep system messages (first N)
        2. Always keep recent messages (last N)
        3. Remove oldest non-essential messages first
        4. If still over limit, truncate long messages
        """
        if not messages:
            return [], TokenStats()

        # Separate message types
        system_msgs = []
        other_msgs = []

        for i, msg in enumerate(messages):
            if isinstance(msg, SystemMessage) and i < self.config.keep_system_messages:
                system_msgs.append(msg)
            else:
                other_msgs.append(msg)

        # Calculate tokens for preserved messages
        system_tokens = sum(self.count_message_tokens(m) for m in system_msgs)

        # Calculate recent messages to keep
        recent_count = min(self.config.keep_recent_messages, len(other_msgs))
        recent_msgs = other_msgs[-recent_count:] if recent_count > 0 else []
        middle_msgs = other_msgs[:-recent_count] if recent_count > 0 else other_msgs

        recent_tokens = sum(self.count_message_tokens(m) for m in recent_msgs)

        # Available tokens for middle messages
        available_for_middle = max_tokens - system_tokens - recent_tokens - 10

        # Select middle messages that fit
        selected_middle = []
        middle_tokens = 0

        # Prioritize more recent middle messages
        for msg in reversed(middle_msgs):
            msg_tokens = self.count_message_tokens(msg)
            if middle_tokens + msg_tokens <= available_for_middle:
                selected_middle.insert(0, msg)
                middle_tokens += msg_tokens

        # Combine: system + selected middle + recent
        result = system_msgs + selected_middle + recent_msgs

        # Calculate final stats
        stats = self.count_messages_tokens(result)
        stats.truncated_count = len(messages) - len(result)

        logger.debug(
            f"[context_manager] Smart truncation: {len(messages)} -> {len(result)} messages, "
            f"{stats.truncated_count} removed"
        )

        return result, stats

    def _truncate_fifo(
        self,
        messages: List[BaseMessage],
        max_tokens: int,
    ) -> Tuple[List[BaseMessage], TokenStats]:
        """
        FIFO truncation: remove oldest messages first.

        Keeps system messages, removes oldest other messages.
        """
        if not messages:
            return [], TokenStats()

        # Separate system messages
        system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
        other_msgs = [m for m in messages if not isinstance(m, SystemMessage)]

        system_tokens = sum(self.count_message_tokens(m) for m in system_msgs)
        available = max_tokens - system_tokens

        # Keep messages from the end until we exceed limit
        result_other = []
        current_tokens = 0

        for msg in reversed(other_msgs):
            msg_tokens = self.count_message_tokens(msg)
            if current_tokens + msg_tokens <= available:
                result_other.insert(0, msg)
                current_tokens += msg_tokens
            else:
                break

        result = system_msgs + result_other
        stats = self.count_messages_tokens(result)
        stats.truncated_count = len(messages) - len(result)

        return result, stats

    def _truncate_middle(
        self,
        messages: List[BaseMessage],
        max_tokens: int,
    ) -> Tuple[List[BaseMessage], TokenStats]:
        """
        Middle truncation: keep start and end, remove middle.

        Good for preserving initial context and recent exchanges.
        """
        if not messages:
            return [], TokenStats()

        n = len(messages)
        if n <= 4:
            return self._truncate_fifo(messages, max_tokens)

        # Keep first 2 and last 2, then add more from each end
        head = messages[:2]
        tail = messages[-2:]
        middle = messages[2:-2]

        head_tokens = sum(self.count_message_tokens(m) for m in head)
        tail_tokens = sum(self.count_message_tokens(m) for m in tail)
        available = max_tokens - head_tokens - tail_tokens

        # Add from middle, alternating head and tail
        selected_middle = []
        current_tokens = 0
        head_idx = 0
        tail_idx = len(middle) - 1

        while head_idx <= tail_idx and current_tokens < available:
            # Add from head
            if head_idx <= tail_idx:
                msg = middle[head_idx]
                msg_tokens = self.count_message_tokens(msg)
                if current_tokens + msg_tokens <= available:
                    selected_middle.append(msg)
                    current_tokens += msg_tokens
                    head_idx += 1
                else:
                    break

            # Add from tail
            if head_idx <= tail_idx:
                msg = middle[tail_idx]
                msg_tokens = self.count_message_tokens(msg)
                if current_tokens + msg_tokens <= available:
                    selected_middle.append(msg)
                    current_tokens += msg_tokens
                    tail_idx -= 1
                else:
                    break

        # Sort selected middle by original order
        selected_middle.sort(key=lambda m: middle.index(m))

        result = head + selected_middle + tail
        stats = self.count_messages_tokens(result)
        stats.truncated_count = len(messages) - len(result)

        return result, stats

    def get_available_tokens(
        self,
        messages: List[BaseMessage],
        reserve_for_response: int = 1000,
    ) -> int:
        """
        Calculate available tokens for new content.

        Args:
            messages: Current messages
            reserve_for_response: Tokens to reserve for model response

        Returns:
            Number of tokens available
        """
        stats = self.count_messages_tokens(messages)
        available = self.max_context_tokens - stats.total_tokens - reserve_for_response
        return max(0, available)

    def should_truncate(
        self,
        messages: List[BaseMessage],
        threshold: float = 0.9,
    ) -> bool:
        """
        Check if messages should be truncated.

        Args:
            messages: Current messages
            threshold: Truncate when usage exceeds this ratio

        Returns:
            True if truncation is recommended
        """
        stats = self.count_messages_tokens(messages)
        usage_ratio = stats.total_tokens / self.max_context_tokens
        return usage_ratio >= threshold

    def summarize_long_message(
        self,
        message: BaseMessage,
        max_tokens: int = 500,
    ) -> BaseMessage:
        """
        Truncate a single long message content.

        Args:
            message: Message to truncate
            max_tokens: Maximum tokens for content

        Returns:
            Truncated message
        """
        content = message.content if hasattr(message, "content") else str(message)
        current_tokens = self.count_tokens(content)

        if current_tokens <= max_tokens:
            return message

        # Truncate content
        if self._encoder:
            tokens = self._encoder.encode(content)
            truncated_tokens = tokens[:max_tokens - 10]
            truncated_content = self._encoder.decode(truncated_tokens)
            truncated_content += "\n... [truncated]"
        else:
            # Character-based truncation
            char_limit = max_tokens * 4
            truncated_content = content[:char_limit] + "\n... [truncated]"

        # Create new message of same type
        if isinstance(message, SystemMessage):
            return SystemMessage(content=truncated_content)
        elif isinstance(message, HumanMessage):
            return HumanMessage(content=truncated_content)
        elif isinstance(message, AIMessage):
            return AIMessage(content=truncated_content)
        elif isinstance(message, ToolMessage):
            return ToolMessage(
                content=truncated_content,
                tool_call_id=getattr(message, "tool_call_id", ""),
            )
        else:
            return message


# Global context manager instances
_context_managers: Dict[str, ContextManager] = {}


def get_context_manager(
    model: str = "gpt-4",
    config: Optional[TruncationConfig] = None,
) -> ContextManager:
    """
    Get or create a ContextManager for a model.

    Args:
        model: Model name
        config: Optional truncation config

    Returns:
        ContextManager instance
    """
    key = f"{model}_{id(config) if config else 'default'}"

    if key not in _context_managers:
        _context_managers[key] = ContextManager(model=model, config=config)

    return _context_managers[key]


def truncate_for_model(
    messages: List[BaseMessage],
    model: str = "gpt-4",
    max_tokens: Optional[int] = None,
) -> List[BaseMessage]:
    """
    Convenience function to truncate messages for a model.

    Args:
        messages: Messages to truncate
        model: Target model
        max_tokens: Maximum tokens (auto-detected if not specified)

    Returns:
        Truncated messages
    """
    manager = get_context_manager(model)

    if max_tokens is None:
        # Use 80% of model's context window
        max_tokens = int(manager.max_context_tokens * 0.8)

    truncated, stats = manager.truncate_messages(messages, max_tokens=max_tokens)

    if stats.truncated_count > 0:
        logger.info(
            f"[context_manager] Truncated {stats.truncated_count} messages for {model}"
        )

    return truncated
