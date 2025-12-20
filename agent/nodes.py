from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.types import Send, interrupt
from typing import Dict, Any, List, Optional, Tuple, Union
import json
import logging
import asyncio
from datetime import datetime
from pydantic import BaseModel, Field
import time
import mimetypes

from .state import AgentState, ResearchPlan, QueryState
from .middleware import enforce_tool_call_limit, retry_call
from tools import tavily_search, execute_python_code
from tools.registry import get_registered_tools
from .deepsearch import run_deepsearch
from .agent_factory import build_writer_agent
from common.config import settings
from common.cancellation import cancellation_manager, check_cancellation as _check_cancellation

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
        "final_report": "任务已被用户取消。"
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
        params.update({
            "azure_endpoint": settings.azure_endpoint or None,
            "azure_deployment": model,
            "api_version": settings.azure_api_version or None,
            "api_key": settings.azure_api_key or settings.openai_api_key,
        })
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


def _extract_tool_call_fields(tool_call: Any) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
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

        normalized.append({
            "url": data_url,
            "name": img.get("name", ""),
            "mime": mime,
        })
    return normalized


def _build_user_content(text: str, images: Optional[List[Dict[str, Any]]]) -> Union[str, List[Dict[str, Any]]]:
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
        parts.append({
            "type": "image_url",
            "image_url": {"url": img["url"]}
        })

    if not parts:
        return ""
    if len(parts) == 1 and parts[0].get("type") == "text":
        return parts[0]["text"]
    return parts


def perform_parallel_search(state: QueryState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Executes a single search query in parallel.
    Includes cancellation check for graceful termination.
    """
    query = state["query"]
    logger.info(f"Executing parallel search for: {query}")

    try:
        # 搜索前检查取消状态
        check_cancellation(state)

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

        # 搜索后检查取消状态
        check_cancellation(state)

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


def deepsearch_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Deep search pipeline that iterates query → search → summarize."""
    logger.info("Executing deepsearch node")
    try:
        _check_cancellation(state)
        return run_deepsearch(state, config)
    except asyncio.CancelledError as e:
        return handle_cancellation(state, e)
    except Exception as e:
        logger.error(f"Deepsearch error: {str(e)}", exc_info=settings.debug)
        msg = f"Deep search failed: {e}"
        return {
            "errors": [msg],
            "final_report": msg,
            "draft_report": msg,
            "is_complete": False,
            "messages": [AIMessage(content=msg)],
        }


def route_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Route execution based on search mode configuration."""
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    mode_info = configurable.get("search_mode", {}) or {}
    route = mode_info.get("mode", "direct")
    max_revisions = configurable.get("max_revisions", state.get("max_revisions", 0))
    logger.info(f"Routing mode: {route}")
    return {"route": route, "max_revisions": max_revisions}


def clarify_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Light-weight guardrail to decide if the query needs clarification before planning.
    Uses structured output with retry for robustness.
    """
    logger.info("Executing clarify node")
    llm = _chat_model(_selected_reasoning_model(config, settings.reasoning_model), temperature=0.3)

    class ClarifyResponse(BaseModel):
        need_clarification: bool = Field(description="Whether the user request is ambiguous or incomplete.")
        question: str = Field(default="", description="A concise clarifying question.")
        verification: str = Field(default="", description="A brief confirmation to proceed when clear.")

    system_msg = SystemMessage(content=(
        "You are a safety check that decides if the user's request needs clarification before research.\n"
        "If the ask is ambiguous, missing key details, or multi-intent, set need_clarification=true and propose ONE concise question.\n"
        "Otherwise, set need_clarification=false and provide a short confirmation to proceed."
    ))
    human_msg = HumanMessage(content=_build_user_content(state.get("input", ""), state.get("images")))

    try:
        response = llm.with_structured_output(ClarifyResponse).with_retry(stop_after_attempt=2).invoke(
            [system_msg, human_msg],
            config=config
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
            "is_complete": True
        }

    logger.info("No clarification needed; proceeding to planning.")
    return {
        "needs_clarification": False,
        "messages": [AIMessage(content=verification)]
    }


def direct_answer_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Direct answer without research."""
    logger.info("Executing direct answer node")
    t0 = time.time()
    llm = _chat_model(_selected_model(config, settings.primary_model), temperature=0.7)
    messages = [
        SystemMessage(content="You are a helpful assistant. Answer succinctly and accurately."),
        HumanMessage(content=_build_user_content(state["input"], state.get("images")))
    ]
    response = llm.invoke(messages, config=config)
    _log_usage(response, "direct_answer")
    logger.info(f"[timing] direct_answer {(time.time()-t0):.3f}s")
    content = response.content if hasattr(response, "content") else str(response)
    return {
        "draft_report": content,
        "final_report": content,
        "messages": [AIMessage(content=content)],
        "is_complete": False
    }


def initiate_research(state: AgentState) -> List[Send]:
    """
    Map step: Generates search tasks for each query in the plan.
    """
    plan = state.get("research_plan", [])
    logger.info(f"Initiating parallel research for {len(plan)} queries")
    
    return [
        Send("perform_parallel_search", {"query": q}) for q in plan
    ]


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
        llm = _chat_model(_selected_reasoning_model(config, settings.reasoning_model), temperature=1)
        t0 = time.time()

        class PlanResponse(BaseModel):
            queries: List[str] = Field(description="3-7 targeted search queries")
            reasoning: str = Field(description="Brief explanation of the research strategy")

        system_msg = SystemMessage(content="You are an expert research planner. Return JSON with 3-7 targeted search queries and a brief reasoning.")
        human_msg = HumanMessage(content=_build_user_content(state["input"], state.get("images")))

        response = llm.with_structured_output(PlanResponse).with_retry(stop_after_attempt=2).invoke(
            [system_msg, human_msg],
            config=config
        )

        # LLM 调用后检查取消状态
        check_cancellation(state)

        _log_usage(response, "planner")
        logger.info(f"[timing] planner {(time.time()-t0):.3f}s")
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
                AIMessage(content=f"Research Plan:\n{reasoning}\n\nQueries:\n" + "\n".join(f"{i+1}. {q}" for i, q in enumerate(queries)))
            ]
        }

    except asyncio.CancelledError as e:
        return handle_cancellation(state, e)
    except Exception as e:
        logger.error(f"Planner error: {str(e)}")
        return {
            "research_plan": [state["input"]],
            "current_step": 0,
            "errors": [f"Planning error: {str(e)}"],
            "messages": [AIMessage(content=f"Using fallback plan: direct search for '{state['input']}'")]
        }


def refine_plan_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Refinement node: creates follow-up queries based on evaluator feedback.
    """
    logger.info("Executing refine plan node (feedback-driven queries)")

    feedback = state.get("evaluation", "") or state.get("verdict", "")
    original_question = state.get("input", "")
    existing_plan = state.get("research_plan", []) or []

    llm = _chat_model(_selected_reasoning_model(config, settings.reasoning_model), temperature=0.8)
    t0 = time.time()

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a research strategist. Generate up to 3 follow-up search queries to close the gaps called out in feedback.

Rules:
- Target missing evidence, data, or counterpoints.
- Avoid repeating prior queries unless wording needs to be more specific.
- Keep queries concise and specific.

Return ONLY a JSON object:
{"queries": ["q1", "q2", ...]}"""),
        ("human", "Question: {question}\nFeedback: {feedback}\nExisting queries: {existing}")
    ])

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
        logger.info(f"[timing] refine_plan {(time.time()-t0):.3f}s")
        content = response.content if hasattr(response, "content") else str(response)
        start = content.find("{")
        end = content.rfind("}") + 1
        new_queries: List[str] = []
        if start >= 0 and end > start:
            try:
                data = json.loads(content[start:end])
                raw_queries = data.get("queries", [])
                seen = {q.lower().strip() for q in existing_plan if isinstance(q, str)}
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

        if not new_queries:
            # Fallback: reuse original question with feedback hint
            new_queries = [f"{original_question} {feedback}".strip()]

        merged_plan = existing_plan + new_queries
        revision_count = int(state.get("revision_count", 0)) + 1

        logger.info(f"Refine plan added {len(new_queries)} queries; total plan size {len(merged_plan)}")
        return {
            "research_plan": merged_plan,
            "revision_count": revision_count,
            "messages": [AIMessage(content="Added follow-up queries:\n" + "\n".join(f"- {q}" for q in new_queries))]
        }
    except Exception as e:
        logger.error(f"Refine plan error: {str(e)}")
        return {
            "research_plan": existing_plan,
            "revision_count": int(state.get("revision_count", 0)) + 1,
            "errors": [f"Refine plan error: {str(e)}"],
            "messages": [AIMessage(content="Continuing with existing plan; failed to create new queries.")]
        }


def web_search_plan_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Simple plan for web search only mode."""
    logger.info("Executing web search plan node")
    return {
        "research_plan": [state["input"]],
        "current_step": 0,
        "messages": [AIMessage(content=f"Web search plan: direct search for '{state['input']}'")]
    }


def writer_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Writer node: Synthesizes research into a comprehensive report.

    Uses collected data to generate a well-structured answer.
    Can invoke code execution for visualizations.
    Includes cancellation check for graceful termination.
    """
    logger.info("Executing writer node (LangChain middleware agent)")

    try:
        check_cancellation(state)

        agent, writer_tools = build_writer_agent(_selected_model(config, settings.primary_model))
        t0 = time.time()
        code_results: List[Dict[str, Any]] = []

        scraped_content = state.get("scraped_content", [])
        blocks: List[str] = []
        sources: List[str] = []
        for idx, item in enumerate(scraped_content):
            query = item.get("query", "")
            results = item.get("results") or []
            blocks.append(f"Search #{idx+1}: {query}")
            for ridx, res in enumerate(results[:3]):
                title = res.get("title", "") or "Untitled"
                url = res.get("url", "")
                summary = res.get("summary") or res.get("snippet") or ""
                tag = f"S{idx+1}-{ridx+1}"
                blocks.append(f"- [{tag}] {title} ({url}) :: {summary[:500]}")
                sources.append(f"[{tag}] {title} - {url}")

        research_context = "\n".join(blocks)
        sources_table = "\n".join(sources)

        messages: List[Any] = [
            SystemMessage(content="You are an expert research analyst. Write a concise, well-structured report with markdown headings, inline source tags like [S1-1], and a Sources section at the end. Use tools if needed (e.g., execute_python_code for charts)."),
            HumanMessage(content=_build_user_content(state["input"], state.get("images"))),
        ]
        if research_context:
            messages.append(HumanMessage(content=f"Research context:\n{research_context}\n\nSources:\n{sources_table}"))

        response = agent.invoke({"messages": messages}, config=config)
        logger.info(f"[timing] writer {(time.time()-t0):.3f}s")

        report = ""
        if isinstance(response, dict) and response.get("messages"):
            last = response["messages"][-1]
            report = getattr(last, "content", "") if hasattr(last, "content") else str(last)
        else:
            report = getattr(response, "content", None) or str(response)

        return {
            "draft_report": report,
            "final_report": report,
            "is_complete": False,
            "messages": [AIMessage(content=report)],
            "code_results": code_results
        }

    except asyncio.CancelledError as e:
        return handle_cancellation(state, e)
    except Exception as e:
        logger.error(f"Writer error: {str(e)}")
        return {
            "final_report": "Error generating report",
            "is_complete": True,
            "errors": [f"Writing error: {str(e)}"],
            "messages": [AIMessage(content=f"Failed to generate report: {str(e)}")]
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
    """Evaluate the draft report and decide if revision is needed."""
    logger.info("Executing evaluator node")
    llm = _chat_model(_selected_reasoning_model(config, settings.reasoning_model), temperature=0)
    t0 = time.time()

    class EvalResponse(BaseModel):
        verdict: str = Field(description='Either "pass" or "revise"')
        feedback: str = Field(description="Actionable feedback if revision is needed.")

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a strict report evaluator. Review the report and decide if it should be revised.

Return ONLY JSON in this format:
{
  "verdict": "pass" | "revise",
  "feedback": "Actionable feedback if revision is needed."
}"""),
        ("human", "Report:\n{report}\n\nQuestion:\n{question}")
    ])

    report = state.get("draft_report") or state.get("final_report", "")
    response = llm.with_structured_output(EvalResponse).invoke(
        prompt.format_messages(report=report, question=state["input"]),
        config=config
    )
    _log_usage(response, "evaluator")
    logger.info(f"[timing] evaluator {(time.time()-t0):.3f}s")
    verdict = response.verdict.lower() if getattr(response, "verdict", None) else "pass"
    feedback = response.feedback if getattr(response, "feedback", None) else ""
    if "revise" in verdict:
        verdict = "revise"
    elif verdict != "pass":
        verdict = "pass"

    logger.info(f"Evaluator verdict: {verdict}")
    return {"evaluation": feedback, "verdict": verdict}


def revise_report_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Revise the report based on evaluator feedback."""
    logger.info("Executing revise report node")
    llm = _chat_model(_selected_model(config, settings.primary_model), temperature=0.5)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a helpful editor. Revise the report using the feedback.
Keep the structure clear and improve factual accuracy and clarity."""),
        ("human", "Question:\n{question}\n\nFeedback:\n{feedback}\n\nCurrent report:\n{report}")
    ])

    report = state.get("draft_report") or state.get("final_report", "")
    feedback = state.get("evaluation", "")
    response = llm.invoke(
        prompt.format_messages(question=state["input"], feedback=feedback, report=report),
        config=config
    )
    content = response.content if hasattr(response, "content") else str(response)

    revision_count = int(state.get("revision_count", 0)) + 1
    return {
        "draft_report": content,
        "final_report": content,
        "revision_count": revision_count,
        "messages": [AIMessage(content=content)],
        "is_complete": False
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
            "messages": [AIMessage(content=report)]
        }

    updated = interrupt({
        "instruction": "Review and edit the report if needed. Return the updated content or approve as-is.",
        "content": report,
    })

    if isinstance(updated, dict):
        if updated.get("content"):
            report = updated["content"]
    elif isinstance(updated, str) and updated.strip():
        report = updated

    return {
        "final_report": report,
        "is_complete": True,
        "messages": [AIMessage(content=report)]
    }
