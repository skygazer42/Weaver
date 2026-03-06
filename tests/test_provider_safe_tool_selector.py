import sys
from pathlib import Path

from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

# Ensure project root is on sys.path for direct test execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.workflows.provider_safe_middleware import ProviderSafeToolSelectorMiddleware


@tool
def alpha_tool() -> str:
    """Alpha tool."""

    return "alpha"


@tool
def beta_tool() -> str:
    """Beta tool."""

    return "beta"


class _FakeStructuredModel:
    def __init__(self, payload):
        self.payload = payload

    def invoke(self, _messages):
        return self.payload

    async def ainvoke(self, _messages):
        return self.payload


class _FakeSelectionModel(BaseChatModel):
    methods: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "fake-selector"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise NotImplementedError

    def with_structured_output(self, _schema, *, method="json_schema", **_kwargs):
        self.methods.append(method)
        if method == "json_schema":
            raise ValueError("response_format unsupported")
        return _FakeStructuredModel({"tools": ["beta_tool"]})


def test_provider_safe_tool_selector_falls_back_to_function_calling():
    model = _FakeSelectionModel()
    middleware = ProviderSafeToolSelectorMiddleware(model=model, max_tools=1)
    captured = {}

    def _handler(request):
        captured["tools"] = [tool.name for tool in request.tools]
        return ModelResponse(result=[])

    request = ModelRequest(
        model=model,
        messages=[HumanMessage("Use the beta tool")],
        tools=[alpha_tool, beta_tool],
    )

    middleware.wrap_model_call(request, _handler)

    assert model.methods == ["json_schema", "function_calling"]
    assert captured["tools"] == ["beta_tool"]


def test_provider_safe_tool_selector_caches_same_request_signature():
    model = _FakeSelectionModel()
    middleware = ProviderSafeToolSelectorMiddleware(
        model=model,
        max_tools=1,
        selection_methods=("function_calling",),
    )
    captured = []

    def _handler(request):
        captured.append([tool.name for tool in request.tools])
        return ModelResponse(result=[])

    request = ModelRequest(
        model=model,
        messages=[HumanMessage("Use the beta tool")],
        tools=[alpha_tool, beta_tool],
    )

    middleware.wrap_model_call(request, _handler)
    middleware.wrap_model_call(request, _handler)

    assert model.methods == ["function_calling"]
    assert captured == [["beta_tool"], ["beta_tool"]]
