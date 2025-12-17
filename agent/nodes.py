from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.types import Send, interrupt
from typing import Dict, Any, List, Optional, Tuple
import json
import logging
from datetime import datetime

from .state import AgentState, ResearchPlan, QueryState
from tools import tavily_search, execute_python_code
from tools.registry import get_registered_tools
from config import settings

logger = logging.getLogger(__name__)


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
    llm = ChatOpenAI(
        model=settings.primary_model,
        temperature=0.7,
        api_key=settings.openai_api_key
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. Answer succinctly and accurately."),
        ("human", "{input}")
    ])
    response = llm.invoke(prompt.format_messages(input=state["input"]), config=config)
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
    llm = ChatOpenAI(
        model=settings.reasoning_model,
        temperature=1,
        api_key=settings.openai_api_key
    )

    planner_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert research planner. Your task is to create a detailed research plan.

Given a user query, break it down into 3-7 specific, targeted search queries that will gather comprehensive information.

Rules:
1. Each query should be focused and specific
2. Queries should cover different aspects of the topic
3. Use varied search terms to avoid redundancy
4. Consider both direct and related information needs

Return ONLY a JSON object with this structure:
{{
    "queries": ["query1", "query2", ...],
    "reasoning": "Brief explanation of the research strategy"
}}""",), 
        ("human", "Create a research plan for: {input}")
    ])

    try:
        response = llm.invoke(planner_prompt.format_messages(input=state["input"]))

        # Parse the response
        content = response.content
        if isinstance(content, str):
            # Extract JSON from response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                plan_data = json.loads(content[start:end])
            else:
                # Fallback: create basic plan
                plan_data = {
                    "queries": [state["input"]],
                    "reasoning": "Direct query"
                }
        else:
            plan_data = {"queries": [state["input"]], "reasoning": "Fallback"}

        queries = plan_data.get("queries", [state["input"]])
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

    llm = ChatOpenAI(
        model=settings.primary_model,
        temperature=0.7,
        api_key=settings.openai_api_key
    ).bind_tools(_get_writer_tools())

    code_results: List[Dict[str, Any]] = []

    # Prepare research context
    scraped_content = state.get("scraped_content", [])
    research_context = "\n\n".join([
        f"Search: {item['query']}\nResults: {json.dumps(item['results'][:3], indent=2)}"
        for item in scraped_content
    ])

    writer_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert research analyst. Synthesize the research findings into a comprehensive, well-structured report.

Guidelines:
1. Start with a clear executive summary
2. Organize information logically
3. Cite sources where relevant
4. Highlight key findings and insights
5. Use markdown formatting
6. If data visualization would help, WRITE PYTHON CODE to create charts using matplotlib.
   - Use the 'execute_python_code' tool.
   - The tool returns an image if you create a plot.
   - Include the analysis of the visualization in your report.

Research Context:
{context}""",), 
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

        report = response.content

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
    llm = ChatOpenAI(
        model=settings.reasoning_model,
        temperature=0,
        api_key=settings.openai_api_key
    )
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
    response = llm.invoke(
        prompt.format_messages(report=report, question=state["input"]),
        config=config
    )
    content = response.content if hasattr(response, "content") else str(response)

    verdict = "pass"
    feedback = ""
    if isinstance(content, str):
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(content[start:end])
                verdict = data.get("verdict", verdict)
                feedback = data.get("feedback", feedback)
            except json.JSONDecodeError:
                pass
        if "revise" in content.lower():
            verdict = "revise"

    logger.info(f"Evaluator verdict: {verdict}")
    return {"evaluation": feedback, "verdict": verdict}


def revise_report_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Revise the report based on evaluator feedback."""
    logger.info("Executing revise report node")
    llm = ChatOpenAI(
        model=settings.primary_model,
        temperature=0.5,
        api_key=settings.openai_api_key
    )
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
