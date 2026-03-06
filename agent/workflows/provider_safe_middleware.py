from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Iterable

from langchain.agents.middleware import LLMToolSelectorMiddleware
from langchain.agents.middleware.tool_selection import (
    _create_tool_selection_response,
    _render_tool_list,
)
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_DEFAULT_SELECTION_METHODS = ("json_schema", "function_calling", "json_mode")


class ProviderSafeToolSelectorMiddleware(LLMToolSelectorMiddleware):
    """
    Tool selector that degrades across structured-output methods instead of failing.

    OpenAI-compatible gateways often diverge on which structured-output path they
    support. The stock LangChain selector assumes `json_schema`, which breaks on
    DeepSeek. This wrapper retries with more compatible methods and falls back to
    the unfiltered toolset if selection itself is unavailable.
    """

    def __init__(
        self,
        *,
        selection_methods: Iterable[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        methods = tuple(selection_methods or _DEFAULT_SELECTION_METHODS)
        self.selection_methods = tuple(method for method in methods if method)
        self._selection_cache: dict[str, list[str]] = {}

    def _selection_cache_key(self, request: Any) -> str:
        payload = {
            "system_message": request.system_message,
            "user_message": request.last_user_message.content,
            "valid_tool_names": request.valid_tool_names,
            "always_include": self.always_include,
            "max_tools": self.max_tools,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)

    def _selection_messages(self, request: Any, *, method: str) -> list[Any]:
        system_message = request.system_message
        if method == "json_mode":
            system_message += (
                "\nReturn only a JSON object with the shape "
                '{"tools":["tool_name_1","tool_name_2"]}. '
                "Do not include markdown or prose.\n"
                f"Available tools:\n{_render_tool_list(request.available_tools)}"
            )
        return [
            {"role": "system", "content": system_message},
            request.last_user_message,
        ]

    def _select_tools_once(
        self,
        request: ModelRequest,
        *,
        method: str,
        is_async: bool,
    ) -> ModelRequest:
        selection_request = self._prepare_selection_request(request)
        if selection_request is None:
            return request
        cache_key = self._selection_cache_key(selection_request)
        cached_names = self._selection_cache.get(cache_key)
        if cached_names is not None:
            return self._process_selection_response(
                {"tools": cached_names},
                selection_request.available_tools,
                selection_request.valid_tool_names,
                request,
            )

        type_adapter = _create_tool_selection_response(selection_request.available_tools)
        schema = type_adapter.json_schema()
        structured_model = selection_request.model.with_structured_output(schema, method=method)
        messages = self._selection_messages(selection_request, method=method)

        if is_async:
            raise RuntimeError("Use _aselect_tools_once for async selection")

        response = structured_model.invoke(messages)
        if not isinstance(response, dict):
            msg = f"Expected dict response, got {type(response)}"
            raise AssertionError(msg)
        self._selection_cache[cache_key] = list(response.get("tools") or [])
        return self._process_selection_response(
            response,
            selection_request.available_tools,
            selection_request.valid_tool_names,
            request,
        )

    async def _aselect_tools_once(self, request: ModelRequest, *, method: str) -> ModelRequest:
        selection_request = self._prepare_selection_request(request)
        if selection_request is None:
            return request
        cache_key = self._selection_cache_key(selection_request)
        cached_names = self._selection_cache.get(cache_key)
        if cached_names is not None:
            return self._process_selection_response(
                {"tools": cached_names},
                selection_request.available_tools,
                selection_request.valid_tool_names,
                request,
            )

        type_adapter = _create_tool_selection_response(selection_request.available_tools)
        schema = type_adapter.json_schema()
        structured_model = selection_request.model.with_structured_output(schema, method=method)
        messages = self._selection_messages(selection_request, method=method)

        response = await structured_model.ainvoke(messages)
        if not isinstance(response, dict):
            msg = f"Expected dict response, got {type(response)}"
            raise AssertionError(msg)
        self._selection_cache[cache_key] = list(response.get("tools") or [])
        return self._process_selection_response(
            response,
            selection_request.available_tools,
            selection_request.valid_tool_names,
            request,
        )

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        last_error: Exception | None = None
        for method in self.selection_methods:
            try:
                return handler(self._select_tools_once(request, method=method, is_async=False))
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Tool selector method %s failed; falling back to next option. Error: %s",
                    method,
                    exc,
                )
        if last_error is not None:
            logger.warning(
                "Tool selector disabled for this request after exhausting methods %s. "
                "Proceeding with full toolset. Last error: %s",
                self.selection_methods,
                last_error,
            )
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        last_error: Exception | None = None
        for method in self.selection_methods:
            try:
                return await handler(await self._aselect_tools_once(request, method=method))
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Tool selector method %s failed; falling back to next option. Error: %s",
                    method,
                    exc,
                )
        if last_error is not None:
            logger.warning(
                "Tool selector disabled for this request after exhausting methods %s. "
                "Proceeding with full toolset. Last error: %s",
                self.selection_methods,
                last_error,
            )
        return await handler(request)
