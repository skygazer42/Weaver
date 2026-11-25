"""OpenAI-compatible gateway `/models` discovery for Weaver.

Supports SiliconFlow, OpenRouter, OneAPI, DeepSeek, Ollama, vLLM, OpenAI, and
other OpenAI-compatible endpoints without leaking credentials.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, ValidationError

from common.siliconflow import list_siliconflow_chat_models

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"

_NON_CHAT_MODEL_RE = re.compile(
    r"(?:"
    r"embedding|embed|rerank|bge-|gte-|e5-|m3e|"
    r"whisper|tts|stt|asr|speech|audio|voice|cosyvoice|fish-speech|sensevoice|funasr|"
    r"dall-e|gpt-image|flux|stable-diffusion|sdxl|kolors|midjourney|wan2\.|cogvideo|sora|video|"
    r"moderation|omni-moderation|realtime|transcribe|text-davinci|text-curie|text-babbage|text-ada|babbage-002|davinci-002"
    r")",
    re.IGNORECASE,
)


class _GatewayModelEntry(BaseModel):
    id: str = Field(min_length=1)


class _GatewayModelCatalog(BaseModel):
    data: list[_GatewayModelEntry] = Field(default_factory=list)


def is_chat_capable_model_id(model_id: str) -> bool:
    """Filter out obvious non-chat models (embeddings, rerankers, TTS/ASR, image-only)."""
    clean = (model_id or "").strip()
    if not clean:
        return False
    return not bool(_NON_CHAT_MODEL_RE.search(clean))


def _is_loopback_base_url(base_url: str) -> bool:
    try:
        host = (urlparse(base_url).hostname or "").strip().lower()
    except Exception:
        return False
    return host in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}


def _models_endpoint(base_url: str) -> str:
    clean = (base_url or "").strip().rstrip("/")
    if not clean:
        clean = DEFAULT_OPENAI_BASE_URL
    if clean.endswith("/models"):
        return clean
    return f"{clean}/models"


async def list_openai_compatible_chat_models(
    base_url: str,
    api_key: str = "",
    *,
    timeout: float = 5.0,
) -> list[str]:
    """Fetch chat-capable model IDs from an OpenAI-compatible `/models` endpoint."""
    endpoint = _models_endpoint(base_url)
    headers: dict[str, str] = {}
    token = (api_key or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(endpoint, headers=headers)
        response.raise_for_status()
        catalog = _GatewayModelCatalog.model_validate_json(response.content)
        seen: set[str] = set()
        models: list[str] = []
        for entry in catalog.data:
            model_id = entry.id.strip()
            if not is_chat_capable_model_id(model_id):
                continue
            key = model_id.lower()
            if key in seen:
                continue
            seen.add(key)
            models.append(model_id)
        return models
    except httpx.HTTPStatusError as error:
        logger.warning(
            "OpenAI-compatible model catalog %s returned HTTP %d",
            endpoint,
            error.response.status_code,
        )
    except (httpx.RequestError, ValidationError) as error:
        logger.warning(
            "OpenAI-compatible model catalog %s unavailable (%s)",
            endpoint,
            type(error).__name__,
        )
    return []


async def discover_gateway_models(settings_obj: Any) -> tuple[list[str], str]:
    """Discover chat models from SiliconFlow or any configured OpenAI-compatible gateway.

    Returns `(models, source)` where `source` is `"siliconflow"`, `"gateway"`, or `"static"`.
    """
    siliconflow_key = (getattr(settings_obj, "siliconflow_api_key", "") or "").strip()
    if siliconflow_key:
        models = await list_siliconflow_chat_models(siliconflow_key)
        return models, "siliconflow" if models else "static"

    if bool(getattr(settings_obj, "use_azure", False)):
        return [], "static"

    base_url = (getattr(settings_obj, "openai_base_url", "") or "").strip()
    api_key = (getattr(settings_obj, "openai_api_key", "") or "").strip()
    if not api_key and not _is_loopback_base_url(base_url):
        return [], "static"

    models = await list_openai_compatible_chat_models(base_url, api_key)
    return models, "gateway" if models else "static"
