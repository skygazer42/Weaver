import httpx
import pytest

from common.config import Settings


@pytest.mark.parametrize("reasoning", ["", "o1-mini", "deepseek-chat"])
def test_siliconflow_key_selects_gateway_and_replaces_legacy_defaults(reasoning):
    settings = Settings(
        _env_file=None,
        siliconflow_api_key=" test-siliconflow-key ",
        openai_api_key="other-key",
        openai_base_url="https://other-gateway.example/v1",
        use_azure=True,
        primary_model="deepseek-chat",
        reasoning_model=reasoning,
    )

    assert settings.openai_base_url == "https://api.siliconflow.cn/v1"
    assert settings.openai_api_key == "test-siliconflow-key"
    assert not settings.use_azure
    assert settings.primary_model == "deepseek-ai/DeepSeek-V4.1-Flash"
    assert settings.reasoning_model == settings.primary_model


def test_siliconflow_key_preserves_configured_model_ids():
    settings = Settings(
        _env_file=None,
        siliconflow_api_key="test-siliconflow-key",
        primary_model="Qwen/Qwen3.5-9B",
        reasoning_model="zai-org/GLM-5.3-Flash",
    )

    assert settings.primary_model == "Qwen/Qwen3.5-9B"
    assert settings.reasoning_model == "zai-org/GLM-5.3-Flash"


def test_blank_siliconflow_key_keeps_existing_gateway():
    settings = Settings(
        _env_file=None,
        siliconflow_api_key=" ",
        openai_api_key="other-key",
        openai_base_url="https://other-gateway.example/v1",
        use_azure=True,
        primary_model="deepseek-chat",
        reasoning_model="o1-mini",
    )

    assert settings.openai_base_url == "https://other-gateway.example/v1"
    assert settings.openai_api_key == "other-key"
    assert settings.use_azure
    assert settings.primary_model == "deepseek-chat"
    assert settings.reasoning_model == "o1-mini"


@pytest.mark.asyncio
@pytest.mark.parametrize("catalog_available", [True, False])
async def test_public_config_returns_siliconflow_model_ids_without_credentials(
    monkeypatch, catalog_available
):
    import main

    api_key = "test-siliconflow-key"
    monkeypatch.setattr(
        main,
        "settings",
        Settings(_env_file=None, siliconflow_api_key=api_key, primary_model="", reasoning_model=""),
    )

    def siliconflow_response(request):
        assert request.method == "GET"
        assert str(request.url) == "https://api.siliconflow.cn/v1/models?sub_type=chat"
        assert request.headers["Authorization"] == f"Bearer {api_key}"
        if not catalog_available:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": "Qwen/Qwen3.5-9B", "object": "model", "owned_by": "Qwen"},
                    {
                        "id": "deepseek-ai/DeepSeek-V4.1-Flash",
                        "object": "model",
                        "owned_by": "deepseek-ai",
                    },
                    {"id": "zai-org/GLM-5.3-Flash", "object": "model", "owned_by": "zai-org"},
                ],
            },
        )

    transport = httpx.MockTransport(siliconflow_response)

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
    assert models["default"] == "deepseek-ai/DeepSeek-V4.1-Flash"
    expected = ["deepseek-ai/DeepSeek-V4.1-Flash"]
    if catalog_available:
        expected += ["Qwen/Qwen3.5-9B", "zai-org/GLM-5.3-Flash"]
    assert models["options"] == expected
