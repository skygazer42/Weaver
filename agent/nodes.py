from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.graph import Send
from typing import Dict, Any, List, Optional
import json
import logging
from datetime import datetime

from .state import AgentState, ResearchPlan, QueryState
from tools import tavily_search, execute_python_code
from config import settings

logger = logging.getLogger(__name__)


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


def writer_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Writer node: Synthesizes research into a comprehensive report.

    Uses collected data to generate a well-structured answer.
    Can invoke code execution for visualizations.
    """
    logger.info("Executing writer node")

    llm = ChatOpenAI(
        model=settings.primary_model,
        temperature=0.7,
        api_key=settings.openai_api_key
    ).bind_tools([execute_python_code])

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
                if tool_call["name"] == "execute_python_code":
                    logger.info("Executing Python code for visualization...")
                    
                    # Execute code with config to trigger events
                    tool_result = execute_python_code.invoke(tool_call["args"], config=config)
                    
                    # Create tool message
                    tool_msg = ToolMessage(
                        tool_call_id=tool_call["id"],
                        content=json.dumps({
                            "stdout": tool_result.get("stdout"),
                            "stderr": tool_result.get("stderr"),
                            "success": tool_result.get("success")
                        }),
                        name=tool_call["name"]
                    )
                    messages.append(tool_msg)
                    
                    # If we got an image, we might want to store it
                    if tool_result.get("image"):
                        state["code_results"].append({
                            "code": tool_call["args"].get("code"),
                            "image": tool_result["image"],
                            "timestamp": datetime.now().isoformat()
                        })
            
            # Second LLM call to generate final report with tool outputs
            response = llm.invoke(messages, config=config)
            logger.info("Final report generated after tool execution")

        report = response.content

        logger.info("Report generated successfully")

        return {
            "final_report": report,
            "is_complete": True,
            "messages": [AIMessage(content=report)]
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