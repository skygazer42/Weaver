"""
Factory to create LangChain agents with official middleware (selector, retry, limits, HITL).
"""

import logging
from typing import List

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    HumanInTheLoopMiddleware,
    LLMToolSelectorMiddleware,
    TodoListMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from common.config import settings
from tools.code.code_executor import execute_python_code
from tools.core.registry import get_registered_tools

logger = logging.getLogger(__name__)


def _build_llm(model: str, temperature: float = 0.7) -> ChatOpenAI:
    params = {
        "model": model,
        "temperature": temperature,
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

    return ChatOpenAI(**params)


def _selector_llm() -> ChatOpenAI:
    return _build_llm(settings.tool_selector_model or "gpt-4o-mini", temperature=0)


def _build_middlewares() -> List:
    mws: List = []

    # Tool selector
    if settings.tool_selector:
        mws.append(
            LLMToolSelectorMiddleware(
                model=_selector_llm(),
                max_tools=settings.tool_selector_max_tools or 3,
                always_include=settings.tool_selector_always_include_list,
                system_prompt=settings.tool_selector_prompt or None,
            )
        )

    # Tool retry
    if settings.tool_retry:
        mws.append(
            ToolRetryMiddleware(
                max_retries=max(settings.tool_retry_max_attempts - 1, 1),
                backoff_factor=settings.tool_retry_backoff or 1.5,
                initial_delay=settings.tool_retry_initial_delay or 1.0,
                max_delay=settings.tool_retry_max_delay or 60.0,
                jitter=True,
                on_failure="return_message",
            )
        )

    # Tool call limit
    if settings.tool_call_limit > 0:
        mws.append(
            ToolCallLimitMiddleware(
                run_limit=settings.tool_call_limit,
                exit_behavior="end",
            )
        )

    # Context editing: clear old tool uses if requested
    if settings.strip_tool_messages:
        mws.append(
            ContextEditingMiddleware(
                edits=[
                    ClearToolUsesEdit(
                        trigger=settings.context_edit_trigger_tokens or 1000,
                        clear_at_least=0,
                        keep=settings.context_edit_keep_tools or 3,
                        clear_tool_inputs=False,
                        exclude_tools=(),
                        placeholder="[cleared]",
                    )
                ],
                token_count_method="approximate",
            )
        )

    # Todo list middleware (optional)
    if settings.enable_todo_middleware:
        mws.append(
            TodoListMiddleware(
                system_prompt=settings.todo_system_prompt or None,
                tool_description=settings.todo_tool_description or None,
            )
        )

    # Human-in-the-loop for risky tools
    if settings.tool_approval:
        # Apply to high-impact tools by default.
        interrupt_cfg = {
            "execute_python_code": True,
            # Lightweight browser tools (network + navigation)
            "browser_search": True,
            "browser_navigate": True,
            "browser_click": True,
            # Sandbox browser tools (network + navigation)
            "sb_browser_navigate": True,
            "sb_browser_click": True,
            "sb_browser_type": True,
            "sb_browser_press": True,
            "sb_browser_scroll": True,
            "sb_browser_extract_text": True,
            "sb_browser_screenshot": True,
            # Crawling helpers (network fetch)
            "crawl_url": True,
            "crawl_urls": True,
        }
        mws.append(
            HumanInTheLoopMiddleware(
                interrupt_on=interrupt_cfg,
                description_prefix="Tool execution pending approval",
            )
        )

    return mws


def build_writer_agent(model: str | None = None) -> tuple[object, List[BaseTool]]:
    """
    Create a tool-calling agent for writer node with configured middleware.
    Returns (agent, tools) so caller can inspect selected toolset.
    """
    model_name = (model or settings.primary_model).strip()
    tools: List[BaseTool] = [execute_python_code]
    tools.extend(get_registered_tools())

    agent = create_agent(
        _build_llm(model_name, temperature=0.7),
        tools,
        middleware=_build_middlewares(),
    )
    return agent, tools


def build_tool_agent(*, model: str, tools: List[BaseTool], temperature: float = 0.7) -> object:
    """
    Create a generic tool-calling agent using the shared middleware stack.
    """
    model_name = (model or settings.primary_model).strip()
    return create_agent(
        _build_llm(model_name, temperature=temperature),
        tools,
        middleware=_build_middlewares(),
    )
