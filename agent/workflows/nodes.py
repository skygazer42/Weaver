import asyncio
import json
import logging
import mimetypes
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.types import Send, interrupt
from pydantic import BaseModel, Field

from agent.core.middleware import enforce_tool_call_limit, retry_call
from agent.core.processor_config import AgentProcessorConfig
from agent.core.state import AgentState, QueryState, ResearchPlan
from agent.workflows.browser_context_helper import build_browser_context_hint
from agent.workflows.response_handler import ResponseHandler
from agent.workflows.stuck_middleware import detect_stuck, inject_stuck_hint
from common.cancellation import cancellation_manager
from common.cancellation import check_cancellation as _check_cancellation
from common.config import settings
from tools import execute_python_code, tavily_search
from tools.core.registry import get_global_registry, get_registered_tools

from .agent_factory import build_tool_agent, build_writer_agent
from .agent_tools import build_agent_tools
from .deepsearch import run_deepsearch

ENHANCED_TOOLS_AVAILABLE = True

logger = logging.getLogger(__name__)


def check_cancellation(state: Union[AgentState, QueryState, Dict[str, Any]]) -> None:
    """
    检查取消状态，如果已取消则抛出 CancelledError

    在长时间操作的关键点调用此函数
    """
    # 检查 state 中的取消标志
    if state.get("is_cancelled"):
        raise asyncio.CancelledError("Task was cancelled (state flag)")

    # 检查取消令牌
    token_id = state.get("cancel_token_id")
    if token_id:
        _check_cancellation(token_id)


def handle_cancellation(state: AgentState, error: Exception) -> Dict[str, Any]:
    """
    处理取消异常，返回取消状态
    """
    logger.info(f"Task cancelled: {error}")
    return {
        "is_cancelled": True,
        "is_complete": True,
        "errors": [f"Cancelled: {str(error)}"],
        "final_report": "任务已被用户取消。",
    }


def _chat_model(
    model: str,
    temperature: float,
    extra_body: Optional[Dict[str, Any]] = None,
) -> ChatOpenAI:
    """
    Build a ChatOpenAI instance honoring custom base URL / Azure / timeout / extra body.
    """
    params: Dict[str, Any] = {
        "temperature": temperature,
        "model": model,
        "api_key": settings.openai_api_key,
        "timeout": settings.openai_timeout or None,
    }

    if settings.use_azure:
        # azure_deployment maps to deployment name; reuse model name by default
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

    # Merge extra body if provided in settings
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


def _log_usage(response: Any, node: str) -> None:
    """Best-effort logging of token usage."""
    if not response:
        return
    usage = None
    if hasattr(response, "usage_metadata"):
        usage = getattr(response, "usage_metadata", None)
    if not usage and hasattr(response, "response_metadata"):
        usage = getattr(response, "response_metadata", None)
    if usage:
        logger.info(f"[usage] {node}: {usage}")


def initialize_enhanced_tools() -> None:
    """
    Initialize enhanced tool system (Phase 1-4).

    Auto-discovers and registers all WeaverTool instances from the tools directory.
    Should be called once at application startup.
    """
    if not ENHANCED_TOOLS_AVAILABLE:
        logger.info("Enhanced tools not available, skipping initialization")
        return

    try:
        registry = get_global_registry()

        # Discover tools from tools directory
        logger.info("Discovering tools from 'tools' directory...")
        discovered = registry.discover_from_directory(
            directory="tools", pattern="*.py", recursive=False, tags=["weaver", "auto_discovered"]
        )

        logger.info(f"Discovered and registered {len(discovered)} tools")

        # Log registered tools
        all_tools = registry.list_names()
        logger.info(f"Total tools in registry: {len(all_tools)}")
        if all_tools:
            logger.info(
                f"Available tools: {', '.join(all_tools[:10])}{'...' if len(all_tools) > 10 else ''}"
            )

    except Exception as e:
        logger.error(f"Failed to initialize enhanced tools: {e}", exc_info=True)


def _configurable(config: RunnableConfig) -> Dict[str, Any]:
    if isinstance(config, dict):
        cfg = config.get("configurable") or {}
        if isinstance(cfg, dict):
            return cfg
    return {}


def _selected_model(config: RunnableConfig, fallback: str) -> str:
    cfg = _configurable(config)
    val = cfg.get("model")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return fallback


def _selected_reasoning_model(config: RunnableConfig, fallback: str) -> str:
    cfg = _configurable(config)
    val = cfg.get("reasoning_model")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return fallback


def _model_for_task(task_type: str, config: RunnableConfig) -> str:
    """
    Get model name for a specific task type using the ModelRouter.

    Respects runtime config overrides, per-task settings, and defaults.
    Falls back to _selected_model/_selected_reasoning_model for compatibility.

    Args:
        task_type: One of: routing, planning, query_gen, research, critique,
                   synthesis, writing, evaluation, reflection, gap_analysis
        config: LangGraph RunnableConfig
    """
    try:
        from agent.core.multi_model import TaskType, get_model_router

        tt = TaskType(task_type)
        router = get_model_router()
        return router.get_model_name(tt, config)
    except Exception:
        # Fallback to legacy behavior
        if task_type in ("planning", "evaluation", "critique", "routing", "reflection", "gap_analysis"):
            return _selected_reasoning_model(config, settings.reasoning_model)
        return _selected_model(config, settings.primary_model)


def _extract_tool_call_fields(
    tool_call: Any,
) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
    """
    Normalize tool call objects across LangChain 0.x/1.x.
    Returns (name, args_dict, tool_call_id).
    """
    if isinstance(tool_call, dict):
        name = tool_call.get("name")
        raw_args = tool_call.get("args") or tool_call.get("arguments")
        tool_call_id = tool_call.get("id") or tool_call.get("tool_call_id")
    else:
        name = getattr(tool_call, "name", None)
        raw_args = getattr(tool_call, "args", None) or getattr(tool_call, "arguments", None)
        tool_call_id = getattr(tool_call, "id", None) or getattr(tool_call, "tool_call_id", None)

    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except json.JSONDecodeError:
            # If LLM sent raw code string, wrap it for the tool signature
            raw_args = {"code": raw_args}
    elif raw_args is None:
        raw_args = {}
    elif not isinstance(raw_args, dict):
        raw_args = {"code": raw_args}

    return name, raw_args, tool_call_id


def _get_writer_tools() -> List[Any]:
    tools: List[Any] = [execute_python_code]
    tools.extend(get_registered_tools())
    return tools


def _guess_mime(name: Optional[str]) -> str:
    mime, _ = mimetypes.guess_type(name or "")
    return mime or "image/png"


def _normalize_images(images: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    """
    Normalize image payloads to data URLs for OpenAI-compatible multimodal inputs.
    Accepts items with either `data` (base64 without prefix) or `url` (already data URL).
    """
    normalized: List[Dict[str, str]] = []
    if not images:
        return normalized

    for img in images:
        if not isinstance(img, dict):
            continue
        raw_data = (img.get("data") or img.get("url") or "").strip()
        if not raw_data:
            continue
        mime = img.get("mime") or _guess_mime(img.get("name"))

        if raw_data.startswith("data:"):
            data_url = raw_data
        else:
            data_url = f"data:{mime};base64,{raw_data}"

        normalized.append(
            {
                "url": data_url,
                "name": img.get("name", ""),
                "mime": mime,
            }
        )
    return normalized


def _build_user_content(
    text: str, images: Optional[List[Dict[str, Any]]]
) -> Union[str, List[Dict[str, Any]]]:
    """
    Build multimodal content for HumanMessage.
    Returns plain text if no images, otherwise a mixed list with text + image_url parts.
    """
    parts: List[Dict[str, Any]] = []
    text = text or ""
    normalized_images = _normalize_images(images)

    if text:
        parts.append({"type": "text", "text": text})
    elif normalized_images:
        # Ensure the model gets some textual anchor when only images are provided
        parts.append({"type": "text", "text": "See attached images and respond accordingly."})

    for img in normalized_images:
        parts.append({"type": "image_url", "image_url": {"url": img["url"]}})

    if not parts:
        return ""
    if len(parts) == 1 and parts[0].get("type") == "text":
        return parts[0]["text"]
    return parts


def perform_parallel_search(state: QueryState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Executes a single search query in parallel.

    Features:
    - LRU cache for duplicate/similar queries
    - Cancellation check for graceful termination
    - Retry support for transient failures
    """
    from .search_cache import get_search_cache

    query = state["query"]
    logger.info(f"Executing parallel search for: {query}")

    try:
        # Check cancellation before search
        check_cancellation(state)

        # Check cache first
        cache = get_search_cache()
        cached_results = cache.get(query)
        if cached_results is not None:
            logger.info(f"[search] Cache hit for: {query[:50]}")
            return {
                "scraped_content": [
                    {
                        "query": query,
                        "results": cached_results,
                        "timestamp": datetime.now().isoformat(),
                        "cached": True,
                    }
                ]
            }

        enforce_tool_call_limit(state, settings.tool_call_limit)

        call_kwargs = {"query": query, "max_results": 5}
        if settings.tool_retry:
            results = retry_call(
                tavily_search.invoke,
                attempts=settings.tool_retry_max_attempts,
                backoff=settings.tool_retry_backoff,
                **{"input": call_kwargs, "config": config},
            )
        else:
            results = tavily_search.invoke(call_kwargs, config=config)

        # Check cancellation after search
        check_cancellation(state)

        # Cache the results
        if results:
            cache.set(query, results)

        search_data = {
            "query": query,
            "results": results,
            "timestamp": datetime.now().isoformat(),
        }

        return {"scraped_content": [search_data]}

    except asyncio.CancelledError as e:
        logger.info(f"Search cancelled for {query}: {e}")
        return {"scraped_content": [], "is_cancelled": True}
    except Exception as e:
        logger.error(f"Parallel search error for {query}: {str(e)}")
        # Return empty result to avoid failing the whole graph
        return {"scraped_content": []}


def coordinator_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Coordinator node that decides the next research action.

    Uses ResearchCoordinator to decide between:
    - plan: generate/refine research plan
    - research: gather more information
    - synthesize: generate report from findings
    - reflect: reflect on progress
    - complete: finish research

    Returns state updates including the coordinator's decision as 'coordinator_action'.
    """
    from agent.workflows.agents import ResearchCoordinator

    logger.info("Executing coordinator node")

    topic = state.get("input", "")
    research_plan = state.get("research_plan", [])
    scraped_content = state.get("scraped_content", [])
    summary_notes = state.get("summary_notes", [])
    revision_count = state.get("revision_count", 0)
    max_revisions = state.get("max_revisions", 2)

    model = _model_for_task("routing", config)
    llm = _chat_model(model, temperature=0.3)

    coordinator = ResearchCoordinator(llm, config)

    # Build knowledge summary from summary_notes
    knowledge_summary = "\n".join(summary_notes[:5]) if summary_notes else ""

    decision = coordinator.decide_next_action(
        topic=topic,
        num_queries=len(research_plan),
        num_sources=len(scraped_content),
        num_summaries=len(summary_notes),
        current_epoch=revision_count,
        max_epochs=max_revisions + 1,
        knowledge_summary=knowledge_summary,
    )

    logger.info(
        f"[coordinator] Decision: {decision.action.value} | "
        f"Reasoning: {decision.reasoning[:100]}"
    )

    return {
        "coordinator_action": decision.action.value,
        "coordinator_reasoning": decision.reasoning,
        "missing_topics": decision.priority_topics if decision.priority_topics else state.get("missing_topics", []),
    }


def deepsearch_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Deep search pipeline that iterates query → search → summarize."""
    logger.info("Executing deepsearch node")
    try:
        token_id = state.get("cancel_token_id")
        if token_id:
            _check_cancellation(token_id)
        return run_deepsearch(state, config)
    except asyncio.CancelledError as e:
        return handle_cancellation(state, e)
    except Exception as e:
        logger.error(f"Deepsearch error: {str(e)}", exc_info=settings.debug)
        err_text = str(e)
        # Provide a clearer hint when the provider rejects the model name
        if "Model Not Exist" in err_text or "model_not_found" in err_text:
            msg = (
                "Deep search failed because the model is not available at your configured provider. "
                "Check OPENAI_BASE_URL/PRIMARY_MODEL and ensure OPENAI_API_KEY matches that provider "
                f"(current PRIMARY_MODEL={settings.primary_model}, BASE_URL={settings.openai_base_url or 'https://api.openai.com/v1'}). "
                "For DeepSeek, set PRIMARY_MODEL=deepseek-chat and use a valid DeepSeek API key."
            )
        else:
            msg = f"Deep search failed: {err_text}"
        return {
            "errors": [msg],
            "final_report": msg,
            "draft_report": msg,
            "is_complete": False,
            "messages": [AIMessage(content=msg)],
        }


def route_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Route execution using SmartRouter (LLM-based intelligent routing).

    Priority:
    1. Config override (search_mode.mode) - for explicit user control
    2. SmartRouter LLM decision - intelligent query classification
    3. Low confidence fallback - route to clarify if confidence < threshold

    Returns state updates with routing decision and metadata.
    """
    from agent.core.smart_router import smart_route

    configurable = _configurable(config)
    mode_info = configurable.get("search_mode", {}) or {}
    override_mode = mode_info.get("mode")
    max_revisions = configurable.get("max_revisions", state.get("max_revisions", 0))
    confidence_threshold = float(configurable.get("routing_confidence_threshold", 0.6))

    # Use SmartRouter (handles override internally)
    result = smart_route(
        query=state.get("input", ""),
        images=state.get("images"),
        config=config,
        override_mode=override_mode if override_mode else None,
    )

    route = result.get("route", "direct")
    confidence = result.get("routing_confidence", 1.0)

    # Low confidence fallback: route to clarify
    if not override_mode and confidence < confidence_threshold:
        logger.info(
            f"Low confidence ({confidence:.2f} < {confidence_threshold}), routing to clarify"
        )
        route = "clarify"
        result["route"] = "clarify"
        result["needs_clarification"] = True

    logger.info(f"[route_node] Routing decision: {route} (confidence: {confidence:.2f})")
    logger.info(f"[route_node] search_mode from config: {mode_info}")
    logger.info(f"[route_node] override_mode: {override_mode}")
    logger.info(f"[route_node] Returning result with route='{route}'")

    # Merge max_revisions into result
    result["max_revisions"] = max_revisions

    # Domain classification (if enabled)
    if getattr(settings, "domain_routing_enabled", False) and route in ("deep", "web"):
        try:
            from agent.workflows.domain_router import DomainClassifier

            domain_llm = _chat_model(_model_for_task("routing", config), temperature=0.3)
            classifier = DomainClassifier(domain_llm, config)

            classification = classifier.classify(state.get("input", ""))

            result["domain"] = classification.domain.value
            result["domain_config"] = classification.to_dict()

            logger.info(
                f"[route_node] Domain classified: {classification.domain.value} "
                f"(confidence: {classification.confidence:.2f})"
            )

        except Exception as e:
            logger.warning(f"[route_node] Domain classification failed: {e}")
            result["domain"] = "general"
            result["domain_config"] = {}

    return result


def clarify_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Light-weight guardrail to decide if the query needs clarification before planning.
    Uses structured output with retry for robustness.
    """
    logger.info("Executing clarify node")
    llm = _chat_model(_model_for_task("routing", config), temperature=0.3)

    class ClarifyResponse(BaseModel):
        need_clarification: bool = Field(
            description="Whether the user request is ambiguous or incomplete."
        )
        question: str = Field(default="", description="A concise clarifying question.")
        verification: str = Field(
            default="", description="A brief confirmation to proceed when clear."
        )

    system_msg = SystemMessage(
        content=(
            "You are a safety check that decides if the user's request needs clarification before research.\n"
            "If the ask is ambiguous, missing key details, or multi-intent, set need_clarification=true and propose ONE concise question.\n"
            "Otherwise, set need_clarification=false and provide a short confirmation to proceed."
        )
    )
    human_msg = HumanMessage(
        content=_build_user_content(state.get("input", ""), state.get("images"))
    )

    try:
        response = (
            llm.with_structured_output(ClarifyResponse)
            .with_retry(stop_after_attempt=2)
            .invoke([system_msg, human_msg], config=config)
        )
        _log_usage(response, "clarify")
    except Exception as e:
        logger.warning(f"Clarify step failed, proceeding without clarification: {e}")
        return {"needs_clarification": False}

    needs_clarification = bool(getattr(response, "need_clarification", False))
    question = getattr(response, "question", "") or "Could you clarify your request?"
    verification = getattr(response, "verification", "") or "Understood. Proceeding."

    if needs_clarification:
        logger.info("Clarification required; returning question to user.")
        return {
            "needs_clarification": True,
            "final_report": question,
            "messages": [AIMessage(content=question)],
            "is_complete": True,
        }

    logger.info("No clarification needed; proceeding to planning.")
    return {"needs_clarification": False, "messages": [AIMessage(content=verification)]}


def direct_answer_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Direct answer without research."""
    logger.info("Executing direct answer node")
    t0 = time.time()
    llm = _chat_model(_model_for_task("writing", config), temperature=0.7)
    messages = [
        SystemMessage(content="You are a helpful assistant. Answer succinctly and accurately."),
        HumanMessage(content=_build_user_content(state["input"], state.get("images"))),
    ]
    response = llm.invoke(messages, config=config)
    _log_usage(response, "direct_answer")
    logger.info(f"[timing] direct_answer {(time.time() - t0):.3f}s")
    content = response.content if hasattr(response, "content") else str(response)
    return {
        "draft_report": content,
        "final_report": content,
        "messages": [AIMessage(content=content)],
        "is_complete": False,
    }


def initiate_research(state: AgentState) -> List[Send]:
    """
    Map step: Generates search tasks for each query in the plan.

    Deduplicates queries before dispatching to avoid redundant searches.
    """
    from .search_cache import QueryDeduplicator

    plan = state.get("research_plan", [])

    # Deduplicate queries
    deduplicator = QueryDeduplicator(similarity_threshold=0.85)
    unique_queries, duplicates = deduplicator.deduplicate(plan)

    if duplicates:
        logger.info(f"Removed {len(duplicates)} duplicate queries from plan")

    logger.info(
        f"Initiating parallel research for {len(unique_queries)} queries (original: {len(plan)})"
    )

    return [Send("perform_parallel_search", {"query": q}) for q in unique_queries]


def planner_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Planning node: Creates a structured research plan.

    Uses a reasoning model (o1-mini or similar) to break down
    the user's query into specific, actionable search steps.
    Includes cancellation check for graceful termination.
    """
    logger.info("Executing planner node")

    try:
        # 规划前检查取消状态
        check_cancellation(state)

        # Use reasoning model for planning
        llm = _chat_model(
            _model_for_task("planning", config), temperature=1
        )
        t0 = time.time()

        class PlanResponse(BaseModel):
            queries: List[str] = Field(description="3-7 targeted search queries")
            reasoning: str = Field(description="Brief explanation of the research strategy")

        system_msg = SystemMessage(
            content="You are an expert research planner. Return JSON with 3-7 targeted search queries and a brief reasoning."
        )
        human_msg = HumanMessage(content=_build_user_content(state["input"], state.get("images")))

        response = (
            llm.with_structured_output(PlanResponse)
            .with_retry(stop_after_attempt=2)
            .invoke([system_msg, human_msg], config=config)
        )

        # LLM 调用后检查取消状态
        check_cancellation(state)

        _log_usage(response, "planner")
        logger.info(f"[timing] planner {(time.time() - t0):.3f}s")
        plan_data = response.dict()

        raw_queries = plan_data.get("queries", [state["input"]])
        # Normalize, dedupe, and clamp to a manageable set
        seen = set()
        queries: List[str] = []
        for q in raw_queries:
            if not isinstance(q, str):
                continue
            q = q.strip()
            if not q or q.lower() in seen:
                continue
            seen.add(q.lower())
            queries.append(q)
            if len(queries) >= 6:
                break
        if not queries:
            queries = [state["input"]]

        reasoning = plan_data.get("reasoning", "")

        logger.info(f"Generated {len(queries)} research queries")

        return {
            "research_plan": queries,
            "current_step": 0,
            "messages": [
                AIMessage(
                    content=f"Research Plan:\n{reasoning}\n\nQueries:\n"
                    + "\n".join(f"{i + 1}. {q}" for i, q in enumerate(queries))
                )
            ],
        }

    except asyncio.CancelledError as e:
        return handle_cancellation(state, e)
    except Exception as e:
        logger.error(f"Planner error: {str(e)}")
        return {
            "research_plan": [state["input"]],
            "current_step": 0,
            "errors": [f"Planning error: {str(e)}"],
            "messages": [
                AIMessage(content=f"Using fallback plan: direct search for '{state['input']}'")
            ],
        }


def refine_plan_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Refinement node: creates follow-up queries based on evaluator feedback.

    Optimization: Uses evaluator's suggested_queries and missing_topics directly
    when available, falling back to LLM generation only when needed.
    """
    logger.info("Executing refine plan node (feedback-driven queries)")

    feedback = state.get("evaluation", "") or state.get("verdict", "")
    original_question = state.get("input", "")
    existing_plan = state.get("research_plan", []) or []
    seen = {q.lower().strip() for q in existing_plan if isinstance(q, str)}

    # Priority 1: Use evaluator's suggested_queries if available
    suggested_queries = state.get("suggested_queries", []) or []
    missing_topics = state.get("missing_topics", []) or []

    new_queries: List[str] = []

    # Add suggested queries (already validated by evaluator)
    for q in suggested_queries:
        if not isinstance(q, str):
            continue
        q_norm = q.strip()
        if q_norm and q_norm.lower() not in seen:
            seen.add(q_norm.lower())
            new_queries.append(q_norm)

    # Generate queries from missing_topics if not enough
    if len(new_queries) < 3 and missing_topics:
        for topic in missing_topics:
            if len(new_queries) >= 3:
                break
            # Create targeted query for missing topic
            topic_query = f"{original_question} {topic}".strip()
            if topic_query.lower() not in seen:
                seen.add(topic_query.lower())
                new_queries.append(topic_query)

    # Priority 2: Fall back to LLM generation if no queries from evaluator
    if not new_queries:
        logger.info("No evaluator suggestions, generating via LLM")
        llm = _chat_model(
            _model_for_task("planning", config), temperature=0.8
        )
        t0 = time.time()

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are a research strategist. Generate up to 3 follow-up search queries to close the gaps called out in feedback.

Rules:
- Target missing evidence, data, or counterpoints.
- Avoid repeating prior queries unless wording needs to be more specific.
- Keep queries concise and specific.

Return ONLY a JSON object:
{"queries": ["q1", "q2", ...]}""",
                ),
                (
                    "human",
                    "Question: {question}\nFeedback: {feedback}\nExisting queries: {existing}",
                ),
            ]
        )

        try:
            response = llm.invoke(
                prompt.format_messages(
                    question=original_question,
                    feedback=feedback,
                    existing="\n".join(existing_plan),
                ),
                config=config,
            )
            _log_usage(response, "refine_plan")
            logger.info(f"[timing] refine_plan LLM {(time.time() - t0):.3f}s")
            content = response.content if hasattr(response, "content") else str(response)
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(content[start:end])
                    raw_queries = data.get("queries", [])
                    for q in raw_queries:
                        if not isinstance(q, str):
                            continue
                        q_norm = q.strip()
                        if not q_norm or q_norm.lower() in seen:
                            continue
                        seen.add(q_norm.lower())
                        new_queries.append(q_norm)
                        if len(new_queries) >= 3:
                            break
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            logger.error(f"Refine plan LLM error: {str(e)}")

    # Final fallback
    if not new_queries:
        new_queries = [f"{original_question} {feedback[:50]}".strip()]

    merged_plan = existing_plan + new_queries
    revision_count = int(state.get("revision_count", 0)) + 1

    logger.info(f"Refine plan added {len(new_queries)} queries; total plan size {len(merged_plan)}")
    return {
        "research_plan": merged_plan,
        "revision_count": revision_count,
        "messages": [
            AIMessage(
                content="Added follow-up queries:\n" + "\n".join(f"- {q}" for q in new_queries)
            )
        ],
    }


def web_search_plan_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Simple plan for web search only mode."""
    logger.info("Executing web search plan node")
    return {
        "research_plan": [state["input"]],
        "current_step": 0,
        "messages": [AIMessage(content=f"Web search plan: direct search for '{state['input']}'")],
    }


def agent_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Agent node: Tool-calling loop (GPTs/Manus-like) with enhanced features.

    Supports:
    - Traditional LangChain tool calling
    - Enhanced XML tool calling (Phase 2) if enabled
    - Auto-continuation detection (Phase 3)
    - Tool registry integration (Phase 4)

    Uses `create_agent` + middleware to let the model decide which tools to call.
    Toolset is assembled from `configurable.agent_profile.enabled_tools`.
    """
    logger.info("Executing agent node (tool-calling)")
    try:
        check_cancellation(state)

        cfg = _configurable(config)
        profile = cfg.get("agent_profile") or {}
        thread_id = str(cfg.get("thread_id") or "default")

        model = _model_for_task("research", config)

        # Try to use enhanced tool registry if available
        tools = build_agent_tools(config)

        # Log enabled tools for debugging
        tool_names = [getattr(t, "name", t.__class__.__name__) for t in tools]
        logger.info(f"Agent loaded {len(tools)} tools: {tool_names}")

        if ENHANCED_TOOLS_AVAILABLE and hasattr(settings, "agent_use_enhanced_registry"):
            try:
                registry = get_global_registry()
                if registry.list_names():
                    # Convert registry tools to LangChain format for compatibility
                    logger.info(
                        f"Using enhanced tool registry with {len(registry.list_names())} tools"
                    )
            except Exception as e:
                logger.warning(f"Failed to use enhanced registry: {e}")

        agent = build_tool_agent(model=model, tools=tools, temperature=0.7)
        t0 = time.time()

        # Build enhanced system prompt with context
        from agent.prompts.system_prompts import get_agent_prompt

        profile_prompt_pack = profile.get("prompt_pack")
        profile_prompt_variant = profile.get("prompt_variant", "full")

        enhanced_system_prompt = get_agent_prompt(
            mode="agent",
            context={
                "current_time": datetime.now(),
                "enabled_tools": [tool.__class__.__name__ for tool in tools] if tools else [],
                "prompt_pack": profile_prompt_pack,
                "prompt_variant": profile_prompt_variant,
            },
        )
        browser_hint = None
        if profile.get("browser_context_helper", settings.enable_browser_context_helper):
            browser_hint = build_browser_context_hint(thread_id)

        # Add XML tool calling instruction if enabled
        if ENHANCED_TOOLS_AVAILABLE and getattr(settings, "agent_xml_tool_calling", False):
            xml_instruction = """\n\nXML Tool Calling Format (optional):
You can also use XML format for tool calls:
<function_calls>
<invoke name="tool_name">
<parameter name="param1">value1</parameter>
<parameter name="param2">value2</parameter>
</invoke>
</function_calls>"""
            enhanced_system_prompt += xml_instruction

        # Build messages list with enhanced system prompt
        messages: List[Any] = []

        # Check if there's already a system message in seeded messages
        seeded = state.get("messages") or []
        has_system_msg = False
        if isinstance(seeded, list):
            for msg in seeded:
                if isinstance(msg, SystemMessage):
                    has_system_msg = True
                    break
            messages.extend(seeded)

        # Add enhanced system prompt if no system message exists
        if not has_system_msg:
            messages.insert(0, SystemMessage(content=enhanced_system_prompt))

        if browser_hint:
            messages.append(SystemMessage(content=browser_hint))

        messages.append(
            HumanMessage(content=_build_user_content(state.get("input", ""), state.get("images")))
        )

        response = agent.invoke({"messages": messages}, config=config)
        logger.info(f"[timing] agent {(time.time() - t0):.3f}s")

        text = ""
        if isinstance(response, dict) and response.get("messages"):
            last = response["messages"][-1]
            text = getattr(last, "content", "") if hasattr(last, "content") else str(last)
        else:
            text = getattr(response, "content", None) or str(response)

        # Stuck detection: if last two AI messages repeat, inject hint
        if detect_stuck(
            response.get("messages", []) if isinstance(response, dict) else [], threshold=1
        ):
            result_messages = response.get("messages", []) if isinstance(response, dict) else []
            result_messages = inject_stuck_hint(result_messages)
            response = {"messages": result_messages}
            text = getattr(result_messages[-1], "content", text)

        # Enhanced: Detect XML tool calls in response if enabled
        continuation_needed = False
        if ENHANCED_TOOLS_AVAILABLE and getattr(settings, "agent_xml_tool_calling", False):
            try:
                from agent.parsers.xml_parser import XMLToolParser

                parser = XMLToolParser()
                xml_calls = parser.parse_content(text)
                if xml_calls:
                    logger.info(f"Detected {len(xml_calls)} XML tool calls in response")
                    # Mark for potential continuation (could be handled by graph logic)
                    continuation_needed = True
            except Exception as e:
                logger.debug(f"XML parsing skipped: {e}")

        result = {
            "draft_report": text,
            "final_report": text,
            "is_complete": False,
            "messages": [AIMessage(content=text)],
        }

        # Add continuation hint if detected
        if continuation_needed:
            result["continuation_needed"] = True
            result["xml_tool_calls_detected"] = True

        return result

    except asyncio.CancelledError as e:
        return handle_cancellation(state, e)
    except Exception as e:
        logger.error(f"Agent node error: {e}", exc_info=settings.debug)
        msg = f"Agent mode failed: {e}"
        return {
            "errors": [msg],
            "final_report": msg,
            "draft_report": msg,
            "is_complete": False,
            "messages": [AIMessage(content=msg)],
        }


def compressor_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Compressor node: Extracts and structures key facts from research.

    Processes scraped_content and summary_notes into compressed_knowledge.
    This structured format improves writer output quality and citation accuracy.
    """
    from agent.workflows.compressor import ResearchCompressor

    logger.info("Executing compressor node")

    topic = state.get("input", "")
    scraped_content = state.get("scraped_content", [])
    summary_notes = state.get("summary_notes", [])

    if not scraped_content:
        logger.info("[compressor] No content to compress")
        return {"compressed_knowledge": {}}

    try:
        model = _model_for_task("research", config)
        llm = _chat_model(model, temperature=0.3)

        compressor = ResearchCompressor(llm, config)

        # Check for existing compressed knowledge
        existing_knowledge = state.get("compressed_knowledge", {})

        # Compress new content
        knowledge = compressor.compress(
            topic=topic,
            scraped_content=scraped_content,
            summary_notes=summary_notes,
        )

        # Merge with existing if present
        if existing_knowledge and existing_knowledge.get("facts"):
            from agent.workflows.compressor import CompressedKnowledge, ExtractedFact

            existing = CompressedKnowledge(
                topic=existing_knowledge.get("topic", topic),
                facts=[
                    ExtractedFact(**f) for f in existing_knowledge.get("facts", [])
                ],
                statistics=existing_knowledge.get("statistics", []),
                key_entities=existing_knowledge.get("key_entities", []),
                summary=existing_knowledge.get("summary", ""),
            )
            knowledge = compressor.merge_knowledge(existing, knowledge)

        compressed_dict = knowledge.to_dict()

        logger.info(
            f"[compressor] Compressed: {len(knowledge.facts)} facts, "
            f"{len(knowledge.statistics)} stats"
        )

        return {"compressed_knowledge": compressed_dict}

    except Exception as e:
        logger.error(f"Compressor error: {e}", exc_info=True)
        return {"compressed_knowledge": {}}


def writer_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Writer node: Synthesizes research into a comprehensive report.

    Uses ResultAggregator for intelligent information fusion:
    - Deduplicates results by URL and content similarity
    - Ranks by relevance to original query
    - Outputs in tiers (primary, supporting, additional)

    Includes cancellation check for graceful termination.
    """
    from .result_aggregator import ResultAggregator

    logger.info("Executing writer node (with ResultAggregator)")

    try:
        check_cancellation(state)

        agent, writer_tools = build_writer_agent(_model_for_task("writing", config))
        t0 = time.time()
        code_results: List[Dict[str, Any]] = []

        # Use ResultAggregator for intelligent fusion
        scraped_content = state.get("scraped_content", [])
        original_query = state.get("input", "")

        aggregator = ResultAggregator(
            similarity_threshold=0.7,
            max_results_per_query=3,
            tier_1_threshold=0.6,
            tier_2_threshold=0.3,
        )
        aggregated = aggregator.aggregate(scraped_content, original_query)

        # Format context for the writer
        research_context, sources_table = aggregated.to_context(
            max_tier_1=5,
            max_tier_2=3,
            max_tier_3=2,
            max_content_length=500,
        )

        logger.info(
            f"[writer] Aggregated {aggregated.total_before} -> {aggregated.total_after} results, "
            f"tiers: {len(aggregated.tier_1)}/{len(aggregated.tier_2)}/{len(aggregated.tier_3)}"
        )

        # Use enhanced writer prompt
        from agent.prompts.system_prompts import get_writer_prompt

        writer_system_prompt = get_writer_prompt()

        messages: List[Any] = [
            SystemMessage(content=writer_system_prompt),
            HumanMessage(content=_build_user_content(state["input"], state.get("images"))),
        ]
        if research_context:
            messages.append(
                HumanMessage(
                    content=f"Research context:\n{research_context}\n\nSources:\n{sources_table}"
                )
            )

        response = agent.invoke({"messages": messages}, config=config)
        logger.info(f"[timing] writer {(time.time() - t0):.3f}s")

        report = ""
        if isinstance(response, dict) and response.get("messages"):
            last = response["messages"][-1]
            report = getattr(last, "content", "") if hasattr(last, "content") else str(last)
        else:
            report = getattr(response, "content", None) or str(response)

        # Generate visualizations if compressed_knowledge available
        compressed_knowledge = state.get("compressed_knowledge", {})
        if compressed_knowledge and getattr(settings, "enable_report_charts", True):
            try:
                from agent.workflows.viz_planner import VizPlanner, embed_charts_in_report

                viz_llm = _chat_model(_model_for_task("writing", config), temperature=0.3)
                viz_planner = VizPlanner(viz_llm, config)

                charts = viz_planner.generate_all_charts(
                    compressed_knowledge,
                    report_text=report,
                    max_charts=3,
                )

                if charts:
                    report = embed_charts_in_report(report, charts, format="markdown")
                    logger.info(f"[writer] Embedded {len(charts)} charts in report")

            except Exception as e:
                logger.warning(f"[writer] Chart generation skipped: {e}")

        return {
            "draft_report": report,
            "final_report": report,
            "is_complete": False,
            "messages": [AIMessage(content=report)],
            "code_results": code_results,
        }

    except asyncio.CancelledError as e:
        return handle_cancellation(state, e)
    except Exception as e:
        logger.error(f"Writer error: {str(e)}")
        return {
            "final_report": "Error generating report",
            "is_complete": True,
            "errors": [f"Writing error: {str(e)}"],
            "messages": [AIMessage(content=f"Failed to generate report: {str(e)}")],
        }


def should_continue_research(state: AgentState) -> str:
    """
    Conditional edge: Decide if more research is needed.

    Returns:
        "continue" if more searches needed
        "write" if ready to synthesize
    """
    current_step = state.get("current_step", 0)
    plan_length = len(state.get("research_plan", []))

    if current_step < plan_length:
        return "continue"
    else:
        return "write"


def evaluator_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Evaluate the draft report with structured, multi-dimensional feedback.

    Provides granular assessment across dimensions:
    - coverage: How well does the report address the question?
    - accuracy: Are claims properly supported by sources?
    - freshness: Is the information current and relevant?
    - coherence: Is the report well-structured and logical?

    Returns actionable feedback including missing topics and suggested queries.
    """
    logger.info("Executing evaluator node (structured)")
    llm = _chat_model(_model_for_task("evaluation", config), temperature=0)
    t0 = time.time()

    class EvalDimensions(BaseModel):
        coverage: float = Field(
            ge=0.0,
            le=1.0,
            description="How well the report addresses all aspects of the question (0-1)",
        )
        accuracy: float = Field(
            ge=0.0, le=1.0, description="How well claims are supported by cited sources (0-1)"
        )
        freshness: float = Field(
            ge=0.0, le=1.0, description="How current and up-to-date the information is (0-1)"
        )
        coherence: float = Field(
            ge=0.0, le=1.0, description="How well-structured and logical the report is (0-1)"
        )

    class EvalResponse(BaseModel):
        verdict: str = Field(description='Evaluation verdict: "pass", "revise", or "incomplete"')
        dimensions: EvalDimensions = Field(description="Scores for each evaluation dimension")
        feedback: str = Field(description="Concise, actionable feedback for improvement")
        missing_topics: List[str] = Field(
            default_factory=list,
            description="Topics or aspects that should be covered but are missing",
        )
        suggested_queries: List[str] = Field(
            default_factory=list, description="Search queries that would help fill gaps"
        )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are a strict report evaluator. Assess the report across multiple dimensions.

## Evaluation Criteria:

1. **Coverage** (0-1): Does the report fully address the question?
   - 1.0: All aspects covered comprehensively
   - 0.7+: Most aspects covered, minor gaps
   - 0.5: Partial coverage, notable gaps
   - <0.5: Major aspects missing

2. **Accuracy** (0-1): Are claims properly sourced?
   - 1.0: All claims cited with source tags
   - 0.7+: Most claims sourced
   - 0.5: Mixed sourcing
   - <0.5: Unsupported claims

3. **Freshness** (0-1): Is the information current?
   - 1.0: Up-to-date, recent sources
   - 0.7+: Mostly current
   - 0.5: Some outdated info
   - <0.5: Significantly outdated

4. **Coherence** (0-1): Is it well-organized?
   - 1.0: Clear structure, logical flow
   - 0.7+: Good organization
   - 0.5: Some structural issues
   - <0.5: Disorganized

## Verdict Rules:
- "pass": All dimensions >= 0.7 and no critical gaps
- "revise": Any dimension 0.5-0.7 or minor gaps
- "incomplete": Any dimension < 0.5 or major missing topics

Provide specific, actionable feedback and search queries to address gaps.""",
            ),
            ("human", "Question:\n{question}\n\nReport:\n{report}"),
        ]
    )

    report = state.get("draft_report") or state.get("final_report", "")

    try:
        response = llm.with_structured_output(EvalResponse).invoke(
            prompt.format_messages(report=report, question=state["input"]), config=config
        )
        _log_usage(response, "evaluator")
        logger.info(f"[timing] evaluator {(time.time() - t0):.3f}s")

        # Extract structured data
        verdict = (response.verdict or "pass").lower().strip()
        if verdict not in ("pass", "revise", "incomplete"):
            verdict = "revise" if "revise" in verdict else "pass"

        dimensions = {}
        if hasattr(response, "dimensions") and response.dimensions:
            dims = response.dimensions
            dimensions = {
                "coverage": getattr(dims, "coverage", 0.7),
                "accuracy": getattr(dims, "accuracy", 0.7),
                "freshness": getattr(dims, "freshness", 0.7),
                "coherence": getattr(dims, "coherence", 0.7),
            }
        else:
            dimensions = {"coverage": 0.7, "accuracy": 0.7, "freshness": 0.7, "coherence": 0.7}

        feedback = getattr(response, "feedback", "") or ""
        missing_topics = list(getattr(response, "missing_topics", []) or [])
        suggested_queries = list(getattr(response, "suggested_queries", []) or [])

        # Smart verdict adjustment based on dimensions
        min_score = min(dimensions.values())
        avg_score = sum(dimensions.values()) / len(dimensions)

        if verdict == "pass" and min_score < 0.6:
            verdict = "revise"
            logger.info(f"Adjusted verdict to 'revise' due to low dimension score: {min_score:.2f}")
        elif verdict == "pass" and missing_topics:
            verdict = "revise"
            logger.info(f"Adjusted verdict to 'revise' due to missing topics: {missing_topics}")

        # Build evaluation summary
        eval_summary = f"Dimensions: {dimensions}\n"
        if missing_topics:
            eval_summary += f"Missing topics: {', '.join(missing_topics)}\n"
        if feedback:
            eval_summary += f"Feedback: {feedback}"

        logger.info(f"Evaluator verdict: {verdict} (avg={avg_score:.2f}, min={min_score:.2f})")

        # Enhanced quality assessment
        try:
            from agent.workflows.quality_assessor import QualityAssessor

            quality_llm = _chat_model(_model_for_task("evaluation", config), temperature=0)
            assessor = QualityAssessor(quality_llm, config)

            scraped_content = state.get("scraped_content", [])
            sources = [s.get("url") for s in state.get("sources", []) if s.get("url")]

            quality_report = assessor.assess(report, scraped_content, sources)

            # Merge quality scores into dimensions
            dimensions["claim_support"] = quality_report.claim_support_score
            dimensions["source_diversity"] = quality_report.source_diversity_score
            dimensions["contradiction_free"] = quality_report.contradiction_free_score

            # Adjust verdict if quality issues found
            if quality_report.overall_score < 0.5 and verdict == "pass":
                verdict = "revise"
                logger.info(f"Adjusted verdict due to quality issues: {quality_report.overall_score:.2f}")

            # Add quality recommendations to feedback
            if quality_report.recommendations:
                eval_summary += f"\nQuality recommendations: {'; '.join(quality_report.recommendations)}"

            logger.info(
                f"Quality assessment: overall={quality_report.overall_score:.2f}, "
                f"claims={quality_report.claim_support_score:.2f}"
            )

        except Exception as e:
            logger.warning(f"Quality assessment skipped: {e}")

        return {
            "evaluation": eval_summary,
            "verdict": verdict,
            "eval_dimensions": dimensions,
            "missing_topics": missing_topics,
            "suggested_queries": suggested_queries if verdict != "pass" else [],
        }

    except Exception as e:
        logger.error(f"Evaluator error: {e}")
        return {"evaluation": f"Evaluation failed: {e}", "verdict": "pass"}


def revise_report_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Revise the report based on evaluator feedback."""
    logger.info("Executing revise report node")
    llm = _chat_model(_model_for_task("writing", config), temperature=0.5)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are a helpful editor. Revise the report using the feedback.
Keep the structure clear and improve factual accuracy and clarity.""",
            ),
            (
                "human",
                "Question:\n{question}\n\nFeedback:\n{feedback}\n\nCurrent report:\n{report}",
            ),
        ]
    )

    report = state.get("draft_report") or state.get("final_report", "")
    feedback = state.get("evaluation", "")
    response = llm.invoke(
        prompt.format_messages(question=state["input"], feedback=feedback, report=report),
        config=config,
    )
    content = response.content if hasattr(response, "content") else str(response)

    revision_count = int(state.get("revision_count", 0)) + 1
    return {
        "draft_report": content,
        "final_report": content,
        "revision_count": revision_count,
        "messages": [AIMessage(content=content)],
        "is_complete": False,
    }


def human_review_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Optional human review step using LangGraph interrupt."""
    logger.info("Executing human review node")
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    allow_interrupts = bool(configurable.get("allow_interrupts"))
    require_review = bool(configurable.get("human_review"))

    report = state.get("final_report") or state.get("draft_report", "")

    if not (allow_interrupts and require_review):
        return {
            "final_report": report,
            "is_complete": True,
            "messages": [AIMessage(content=report)],
        }

    updated = interrupt(
        {
            "instruction": "Review and edit the report if needed. Return the updated content or approve as-is.",
            "content": report,
        }
    )

    if isinstance(updated, dict):
        if updated.get("content"):
            report = updated["content"]
    elif isinstance(updated, str) and updated.strip():
        report = updated

    return {"final_report": report, "is_complete": True, "messages": [AIMessage(content=report)]}
