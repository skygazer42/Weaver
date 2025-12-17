from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.types import Send, interrupt
from typing import Dict, Any, List, Optional, Tuple
import json
import logging
from datetime import datetime
from pydantic import BaseModel, Field
import time

from .state import AgentState, ResearchPlan, QueryState
from tools import tavily_search, execute_python_code
from tools.registry import get_registered_tools
from config import settings

logger = logging.getLogger(__name__)


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


def perform_parallel_search(state: QueryState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Executes a single search query in parallel.
    """
    query = state["query"]
    logger.info(f"Executing parallel search for: {query}")
    
    try:
        results = tavily_search.invoke({"query": query, "max_results": 5}, config=config)
        
        search_data = {
            "query": query,
            "results": results,
            "timestamp": datetime.now().isoformat(),
        }
        
        return {"scraped_content": [search_data]}
        
    except Exception as e:
        logger.error(f"Parallel search error for {query}: {str(e)}")
        # Return empty result to avoid failing the whole graph
        return {"scraped_content": []}


def route_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Route execution based on search mode configuration."""
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    mode_info = configurable.get("search_mode", {}) or {}
    route = mode_info.get("mode", "direct")
    max_revisions = configurable.get("max_revisions", state.get("max_revisions", 0))
    logger.info(f"Routing mode: {route}")
    return {"route": route, "max_revisions": max_revisions}


def direct_answer_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Direct answer without research."""
    logger.info("Executing direct answer node")
    t0 = time.time()
    llm = _chat_model(settings.primary_model, temperature=0.7)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. Answer succinctly and accurately."),
        ("human", "{input}")
    ])
    response = llm.invoke(prompt.format_messages(input=state["input"]), config=config)
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


def planner_node(state: AgentState) -> Dict[str, Any]:
    """
    Planning node: Creates a structured research plan.

    Uses a reasoning model (o1-mini or similar) to break down
    the user's query into specific, actionable search steps.
    """
    logger.info("Executing planner node")

    # Use reasoning model for planning
    llm = _chat_model(settings.reasoning_model, temperature=1)
    t0 = time.time()

    class PlanResponse(BaseModel):
        queries: List[str] = Field(description="3-7 targeted search queries")
        reasoning: str = Field(description="Brief explanation of the research strategy")

    planner_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert research planner. Return JSON with 3-7 targeted search queries and a brief reasoning."),
        ("human", "Create a research plan for: {input}")
    ])

    try:
        response = llm.with_structured_output(PlanResponse).invoke(
            planner_prompt.format_messages(input=state["input"])
        )
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

    except Exception as e:
        logger.error(f"Planner error: {str(e)}")
        return {
            "research_plan": [state["input"]],
            "current_step": 0,
            "errors": [f"Planning error: {str(e)}"],
            "messages": [AIMessage(content=f"Using fallback plan: direct search for '{state['input']}'")]
        }


def refine_plan_node(state: AgentState) -> Dict[str, Any]:
    """
    Refinement node: creates follow-up queries based on evaluator feedback.
    """
    logger.info("Executing refine plan node (feedback-driven queries)")

    feedback = state.get("evaluation", "") or state.get("verdict", "")
    original_question = state.get("input", "")
    existing_plan = state.get("research_plan", []) or []

    llm = _chat_model(settings.reasoning_model, temperature=0.8)
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
        response = llm.invoke(prompt.format_messages(
            question=original_question,
            feedback=feedback,
            existing="\n".join(existing_plan)
        ))
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


def web_search_plan_node(state: AgentState) -> Dict[str, Any]:
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
    """
    logger.info("Executing writer node")

    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    allow_interrupts = bool(configurable.get("allow_interrupts"))
    require_tool_approval = bool(configurable.get("tool_approval"))

    llm = _chat_model(settings.primary_model, temperature=0.7).bind_tools(_get_writer_tools())
    t0 = time.time()

    code_results: List[Dict[str, Any]] = []

    # Prepare research context
    scraped_content_raw = state.get("scraped_content", [])

    # Compact and clean scraped content to avoid bloat
    def _compact_scraped(items: List[Dict[str, Any]], max_results: int = 3) -> List[Dict[str, Any]]:
        compact: List[Dict[str, Any]] = []
        for item in items:
            results = item.get("results") or []
            if not results:
                continue
            compact.append({
                "query": item.get("query", ""),
                "results": results[:max_results]
            })
        return compact

    scraped_content = _compact_scraped(scraped_content_raw)

    def _build_research_context(items: List[Dict[str, Any]], budget: int = 8000) -> tuple[str, str]:
        """
        Keep context compact: show top results with summary/snippet only.
        Returns (context_text, sources_table).
        """
        blocks: List[str] = []
        sources: List[str] = []
        remaining = budget

        for idx, item in enumerate(items):
            query = item.get("query", "")
            header = f"Search #{idx+1}: {query}"
            if remaining - len(header) <= 0:
                break
            blocks.append(header)
            remaining -= len(header)

            results = item.get("results", []) or []
            for ridx, res in enumerate(results):
                if remaining <= 0:
                    break
                title = res.get("title", "") or "Untitled"
                url = res.get("url", "")
                summary = res.get("summary") or res.get("snippet") or res.get("content", "")
                summary = (summary or "")[:600]
                tag = f"S{idx+1}-{ridx+1}"
                entry = f"  [{tag}] {title} ({url}) -> {summary}"
                remaining -= len(entry)
                if remaining <= 0:
                    break
                blocks.append(entry)
                sources.append(f"[{tag}] {title} - {url}")

        return "\n".join(blocks), "\n".join(sources)

    research_context, sources_table = _build_research_context(scraped_content)

    # If no research context (e.g., search failed), fall back to direct answer style
    if not research_context.strip():
        logger.info("No research context available; falling back to direct answer mode inside writer.")
        fallback_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant. Answer succinctly and accurately."),
            ("human", "{input}")
        ])
        response = llm.invoke(
            fallback_prompt.format_messages(input=state["input"]),
            config=config
        )
        _log_usage(response, "writer_fallback")
        logger.info(f"[timing] writer_fallback {(time.time()-t0):.3f}s")
        content = response.content if hasattr(response, "content") else str(response)
        return {
            "draft_report": content,
            "final_report": content,
            "is_complete": False,
            "messages": [AIMessage(content=content)],
            "code_results": code_results
        }

    writer_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert research analyst. Synthesize the research findings into a concise, well-structured report.

Guidelines:
1. Lead with a brief executive summary.
2. Use markdown and bullets; keep paragraphs tight.
3. Cite sources inline like [S1-1] where S1 = search #, -1 = result index (see Sources list).
4. Prefer the provided summaries/snippets; do not paste long raw text.
5. Highlight key findings, contrasts, and open questions.
6. If a visualization helps, WRITE PYTHON CODE using matplotlib with the 'execute_python_code' tool and interpret the chart.
7. End with a "Sources" section listing each tag and URL: e.g., - [S1-1] Title — URL.

Research Context (compact):
{context}

Sources:
{sources}""",), 
        ("human", "Create a comprehensive report answering: {query}")
    ])

    try:
        # First LLM call - might decide to use tools
        messages = writer_prompt.format_messages(
            context=research_context[:15000],  # Increased context size
            query=state["input"]
        )
        
        response = llm.invoke(messages, config=config)
        messages.append(response)
        _log_usage(response, "writer_pass1")

        # Handle tool calls
        if response.tool_calls:
            logger.info(f"Writer decided to use tools: {len(response.tool_calls)}")
            
            for tool_call in response.tool_calls:
                tool_name, tool_args, tool_call_id = _extract_tool_call_fields(tool_call)

                if tool_name == "execute_python_code":
                    logger.info("Preparing to execute Python code for visualization...")

                    # Optional approval interrupt
                    if require_tool_approval and allow_interrupts:
                        approval = interrupt({
                            "action": "execute_python_code",
                            "code": tool_args.get("code", ""),
                            "message": "Approve or edit code before execution."
                        })
                        # approval could be boolean or edited payload
                        if isinstance(approval, dict):
                            if approval.get("reject"):
                                logger.info("Code execution rejected by reviewer.")
                                continue
                            if "code" in approval:
                                tool_args["code"] = approval["code"]
                        elif approval is False:
                            logger.info("Code execution rejected (boolean).")
                            continue

                    # Execute code with config to trigger events
                    tool_result = execute_python_code.invoke(tool_args, config=config)
                    
                    # Create tool message
                    tool_msg = ToolMessage(
                        tool_call_id=tool_call_id or f"{tool_name}_call",
                        content=json.dumps({
                            "stdout": tool_result.get("stdout"),
                            "stderr": tool_result.get("stderr"),
                            "success": tool_result.get("success")
                        }),
                        name=tool_name
                    )
                    messages.append(tool_msg)
                    
                    # If we got an image, we might want to store it
                    if tool_result.get("image"):
                        code_results.append({
                            "code": tool_args.get("code"),
                            "image": tool_result["image"],
                            "timestamp": datetime.now().isoformat()
                        })
            
            # Second LLM call to generate final report with tool outputs
            response = llm.invoke(messages, config=config)
            logger.info("Final report generated after tool execution")
            _log_usage(response, "writer_pass2")

        report = response.content
        logger.info(f"[timing] writer {(time.time()-t0):.3f}s")

        logger.info("Report generated successfully")

        return {
            "draft_report": report,
            "final_report": report,
            "is_complete": False,  # further steps may follow (evaluator/human review)
            "messages": [AIMessage(content=report)],
            "code_results": code_results
        }

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
    llm = _chat_model(settings.reasoning_model, temperature=0)
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
    llm = _chat_model(settings.primary_model, temperature=0.5)
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
