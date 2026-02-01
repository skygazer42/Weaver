"""
Centralized LLM Factory for Weaver.

Provides unified model initialization across all modules.
Replaces duplicated _chat_model() functions.
"""

import json
import logging
from typing import Any, Dict, Optional

from langchain_openai import ChatOpenAI

from common.config import settings

logger = logging.getLogger(__name__)


def create_chat_model(
    model: str,
    temperature: float,
    extra_body: Optional[Dict[str, Any]] = None,
) -> ChatOpenAI:
    """
    Create a ChatOpenAI instance with proper configuration.

    Handles:
    - OpenAI API
    - Azure OpenAI
    - Custom base URLs
    - Extra body parameters

    Args:
        model: Model name/deployment
        temperature: Sampling temperature
        extra_body: Optional extra parameters for the API call

    Returns:
        Configured ChatOpenAI instance
    """
    params: Dict[str, Any] = {
        "temperature": temperature,
        "model": model,
        "api_key": settings.openai_api_key,
        "timeout": settings.openai_timeout or None,
    }

    if settings.use_azure:
        params.update(
            {
                "azure_endpoint": settings.azure_endpoint or None,
                "azure_deployment": model,
                "api_version": settings.azure_api_version or None,
                "api_key": settings.azure_api_key or settings.openai_api_key,
            }
        )
    elif settings.openai_base_url:
        params["base_url"] = settings.openai_base_url

    # Merge extra body parameters
    merged_extra: Dict[str, Any] = {}
    if settings.openai_extra_body:
        try:
            merged_extra.update(json.loads(settings.openai_extra_body))
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in openai_extra_body; ignoring.")
    if extra_body:
        merged_extra.update(extra_body)
    if merged_extra:
        params["extra_body"] = merged_extra

    return ChatOpenAI(**params)


def create_summary_model() -> ChatOpenAI:
    """
    Create a ChatOpenAI instance for message summarization.

    Uses settings.summary_messages_model or falls back to primary_model.
    Always uses temperature=0 for deterministic summarization.
    """
    model = settings.summary_messages_model or settings.primary_model
    return create_chat_model(model, temperature=0)


# Aliases for backward compatibility
build_chat_model = create_chat_model
