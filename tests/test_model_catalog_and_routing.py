import httpx
import pytest

from common.config import Settings
from common.model_catalog import (
    discover_gateway_models,
    is_chat_capable_model_id,
    list_openai_compatible_chat_models,
)


def test_is_chat_capable_model_id_filters_non_chat_models():
    assert is_chat_capable_model_id("openai/gpt-4.1")
    assert is_chat_capable_model_id("deepseek-reasoner")
    assert is_chat_capable_model_id("qwen3:32b")
    assert is_chat_capable_model_id("anthropic/claude-sonnet-4")

    assert not is_chat_capable_model_id("text-embedding-3-small")
    assert not is_chat_capable_model_id("BAAI/bge-m3")
    assert not is_chat_capable_model_id("BAAI/bge-reranker-v2-m3")
    assert not is_chat_capable_model_id("whisper-1")
    assert not is_chat_capable_model_id("tts-1-hd")
    assert not is_chat_capable_model_id("black-forest-labs/FLUX.1-dev")
    assert not is_chat_capable_model_id("omni-moderation-latest")
    assert not is_chat_capable_model_id("")


@pytest.mark.asyncio
async def test_generic_gateway_discovers_models_and_filters_non_chat(monkeypatch):
    api_key = "sk-openrouter-test-key"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "https://openrouter.ai/api/v1/models"
        assert request.headers["Authorization"] == f"Bearer {api_key}"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "anthropic/claude-sonnet-4"},
                    {"id": "openai/text-embedding-3-large"},
                    {"id": "deepseek/deepseek-r1"},
                    {"id": "deepseek/deepseek-r1"},
                    {"id": "openai/whisper-1"},
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    async def handle_request(_self, request):
        return await transport.handle_async_request(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle_request)
    models = await list_openai_compatible_chat_models("https://openrouter.ai/api/v1/", api_key)
    assert models == ["anthropic/claude-sonnet-4", "deepseek/deepseek-r1"]


@pytest.mark.asyncio
async def test_loopback_ollama_discovers_models_without_api_key(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://127.0.0.1:11434/v1/models"
        assert "Authorization" not in request.headers
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "qwen3:14b"},
                    {"id": "deepseek-r1:32b"},
                    {"id": "nomic-embed-text:latest"},
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    async def handle_request(_self, request):
        return await transport.handle_async_request(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle_request)
    cfg = Settings(
        _env_file=None,
        siliconflow_api_key="",
        openai_api_key="",
        openai_base_url="http://127.0.0.1:11434/v1",
        primary_model="qwen3:14b",
        reasoning_model="deepseek-r1:32b",
    )
    models, source = await discover_gateway_models(cfg)
    assert source == "gateway"
    assert models == ["qwen3:14b", "deepseek-r1:32b"]


@pytest.mark.asyncio
async def test_public_config_exposes_gateway_models_and_reasoning_default(monkeypatch):
    import main

    api_key = "sk-oneapi-secret"
    monkeypatch.setattr(
        main,
        "settings",
        Settings(
            _env_file=None,
            siliconflow_api_key="",
            openai_api_key=api_key,
            openai_base_url="https://gateway.example.com/v1",
            primary_model="gpt-4.1",
            reasoning_model="deepseek-reasoner",
        ),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://gateway.example.com/v1/models"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "gpt-4.1"},
                    {"id": "deepseek-reasoner"},
                    {"id": "claude-sonnet-4"},
                    {"id": "text-embedding-3-small"},
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    async def handle_request(_self, request):
        return await transport.handle_async_request(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle_request)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        response = await client.get("/api/config/public")

    assert response.status_code == 200
    assert api_key not in response.text
    models = response.json()["models"]
    assert models["default"] == "gpt-4.1"
    assert models["reasoning_default"] == "deepseek-reasoner"
    assert models["source"] == "gateway"
    assert models["options"] == ["gpt-4.1", "deepseek-reasoner", "claude-sonnet-4"]


@pytest.mark.asyncio
async def test_public_config_falls_back_when_gateway_models_unavailable(monkeypatch):
    import main

    monkeypatch.setattr(
        main,
        "settings",
        Settings(
            _env_file=None,
            siliconflow_api_key="",
            openai_api_key="sk-deepseek-key",
            openai_base_url="https://api.deepseek.com/v1",
            primary_model="deepseek-chat",
            reasoning_model="deepseek-reasoner",
        ),
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    async def handle_request(_self, request):
        return await transport.handle_async_request(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle_request)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        response = await client.get("/api/config/public")

    assert response.status_code == 200
    models = response.json()["models"]
    assert models["source"] == "static"
    assert models["default"] == "deepseek-chat"
    assert models["reasoning_default"] == "deepseek-reasoner"
    assert "deepseek-chat" in models["options"]
    assert "deepseek-reasoner" in models["options"]


def test_chat_request_accepts_reasoning_model():
    import main

    req = main.ChatRequest(
        messages=[main.Message(role="user", content="Compare LangGraph and AutoGen")],
        model="deepseek-chat",
        reasoning_model="deepseek-reasoner",
    )
    assert req.model == "deepseek-chat"
    assert req.reasoning_model == "deepseek-reasoner"
