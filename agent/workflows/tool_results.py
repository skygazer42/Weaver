"""Keep full tool output local while the model reads bounded pages."""

import logging
from typing import ClassVar

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately

from agent.core.events import ToolEventType, get_emitter_sync
from common.thread_ownership import get_thread_owner
from common.tool_artifacts import get_tool_artifact, save_tool_artifact

PAGE_CHARS = 4000
logger = logging.getLogger(__name__)
_ARTIFACT_CONTENT = "weaver_full_tool_result"
_ARTIFACT_ID = "weaver_tool_artifact_id"


def _run_identity(runtime: ToolRuntime):
    thread_id = runtime.config.get("configurable", {}).get("thread_id")
    return thread_id, get_thread_owner(thread_id) if thread_id else None


def _has_saved_result(message):
    return (
        isinstance(message, ToolMessage)
        and isinstance(message.artifact, dict)
        and (_ARTIFACT_CONTENT in message.artifact or _ARTIFACT_ID in message.artifact)
    )


@tool
def read_tool_result(artifact_id: str, runtime: ToolRuntime, offset: int = 0) -> str:
    """Read one page of a saved tool result in the current run."""
    if offset < 0:
        return "Offset must be non-negative."
    for message in reversed(runtime.state.get("messages", [])):
        if (
            _has_saved_result(message)
            and (message.artifact.get(_ARTIFACT_ID) or message.tool_call_id) == artifact_id
        ):
            if _ARTIFACT_ID in message.artifact:
                thread_id, owner = _run_identity(runtime)
                saved = (
                    get_tool_artifact(message.artifact[_ARTIFACT_ID], owner, thread_id=thread_id)
                    if owner
                    else None
                )
                if saved is None:
                    return "This run has no saved result for that tool call."
                content = saved.content
            else:
                content = message.artifact[_ARTIFACT_CONTENT]
            if offset >= len(content):
                return "End of result."
            next_offset = min(len(content), offset + PAGE_CHARS)
            header = f"Characters {offset} through {next_offset - 1} of {len(content)}. " + (
                f"Next offset {next_offset}." if next_offset < len(content) else "End of result."
            )
            return f"{header}\n\n{content[offset:next_offset]}"
    return "This run has no saved result for that tool call."


def _limit_result(result, runtime):
    if (
        not isinstance(result, ToolMessage)
        or result.status == "error"
        or result.name == read_tool_result.name
        or not isinstance(result.content, str)
        or len(result.content) <= PAGE_CHARS
    ):
        return result
    content = result.content
    thread_id, owner = _run_identity(runtime)
    saved = (
        save_tool_artifact(thread_id, owner, result.tool_call_id, content)
        if thread_id and owner
        else None
    )
    if saved is not None:
        content = saved.content
    preview = (
        f"{content[:PAGE_CHARS]}\n\n"
        f"Showing the first {PAGE_CHARS} of {len(content)} characters. "
        f"Use read_tool_result with artifact_id={saved.id if saved else result.tool_call_id} and offset={PAGE_CHARS} "
        "to continue reading."
    )
    artifact = {"original_artifact": result.artifact}
    if saved is None:
        artifact[_ARTIFACT_CONTENT] = content
    else:
        artifact[_ARTIFACT_ID] = saved.id
        get_emitter_sync(thread_id).emit_sync(
            ToolEventType.ARTIFACT,
            {
                "id": saved.id,
                "type": "tool_output",
                "title": result.name or "Tool output",
                "content": preview,
                "download_url": f"/api/tool-artifacts/{saved.id}",
                "tool_call_id": result.tool_call_id,
            },
        )
    return result.model_copy(update={"content": preview, "artifact": artifact})


def _reader_when_needed(request: ModelRequest) -> ModelRequest:
    if any(_has_saved_result(message) for message in request.messages):
        return request
    return request.override(tools=[tool for tool in request.tools if tool is not read_tool_result])


def _input_tokens(request: ModelRequest) -> int:
    messages = (
        [request.system_message, *request.messages] if request.system_message else request.messages
    )
    return count_tokens_approximately(messages, tools=request.tools)


def _prepare_model_request(request: ModelRequest) -> ModelRequest:
    selected = _reader_when_needed(request)
    profile = getattr(selected.model, "profile", None) or {}
    limit = profile.get("max_input_tokens")
    if isinstance(limit, int) and limit > 0:
        reserve = getattr(selected.model, "max_tokens", None) or min(
            profile.get("max_output_tokens") or 2048, 2048
        )
        budget = max(1, limit - reserve)
        if _input_tokens(selected) > budget:
            messages = list(selected.messages)
            latest = len(messages)
            while latest and isinstance(messages[latest - 1], ToolMessage):
                latest -= 1
            for index, message in enumerate(messages[:latest]):
                if _has_saved_result(message):
                    identifier = message.artifact.get(_ARTIFACT_ID) or message.tool_call_id
                    messages[index] = message.model_copy(
                        update={"content": f"Earlier output. Read artifact_id={identifier} with read_tool_result."},
                    )
            selected = selected.override(messages=messages)
            if _input_tokens(selected) > budget:
                raise ValueError("The Agent input exceeds the selected model's context budget.")
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Agent estimated input tokens: %s", _input_tokens(selected))
    return selected


def _log_provider_usage(response):
    messages = response.result if isinstance(response, ModelResponse) else [response]
    for message in messages:
        if isinstance(message, AIMessage) and message.usage_metadata:
            logger.debug("Agent provider token usage: %s", message.usage_metadata)
    return response


class ToolResultBudgetMiddleware(AgentMiddleware):
    tools: ClassVar = [read_tool_result]

    def wrap_tool_call(self, request, handler):
        return _limit_result(handler(request), request.runtime)

    async def awrap_tool_call(self, request, handler):
        return _limit_result(await handler(request), request.runtime)

    def wrap_model_call(self, request, handler):
        return _log_provider_usage(handler(_prepare_model_request(request)))

    async def awrap_model_call(self, request, handler):
        return _log_provider_usage(await handler(_prepare_model_request(request)))
