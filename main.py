from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import logging
import asyncio
from datetime import datetime

from config import settings
from langgraph.types import Command
from agent import create_research_graph, create_checkpointer, AgentState
from tools.mcp import init_mcp_tools, close_mcp_tools
from tools.registry import set_registered_tools

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.debug else logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Manus Research Agent API",
    description="Deep research AI agent with code execution capabilities",
    version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize agent graph
checkpointer = create_checkpointer(settings.database_url) if settings.database_url else None
research_graph = create_research_graph(checkpointer=checkpointer)


@app.on_event("startup")
async def startup_event():
    try:
        mcp_tools = await init_mcp_tools()
        if mcp_tools:
            set_registered_tools(mcp_tools)
            logger.info(f"Registered {len(mcp_tools)} MCP tools")
    except Exception as e:
        logger.warning(f"MCP tools startup failed: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    try:
        await close_mcp_tools()
    except Exception:
        pass


# Request/Response models
class Message(BaseModel):
    role: str
    content: str


class SearchMode(BaseModel):
    useWebSearch: bool = False
    useAgent: bool = False
    useDeepSearch: bool = False


class ChatRequest(BaseModel):
    messages: List[Message]
    stream: bool = True
    model: Optional[str] = "gpt-4o"
    search_mode: Optional[SearchMode | Dict[str, Any] | str] = None  # {"useWebSearch": bool, "useAgent": bool, "useDeepSearch": bool}


class ChatResponse(BaseModel):
    id: str
    content: str
    role: str = "assistant"
    timestamp: str


class ResumeRequest(BaseModel):
    thread_id: str
    payload: Any
    model: Optional[str] = "gpt-4o"
    search_mode: Optional[SearchMode | Dict[str, Any] | str] = None


def _serialize_interrupts(interrupts: Any) -> List[Any]:
    if not interrupts:
        return []
    result: List[Any] = []
    for item in interrupts:
        if hasattr(item, "value"):
            result.append(item.value)
        elif isinstance(item, dict):
            result.append(item)
        else:
            result.append(str(item))
    return result


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Manus Research Agent",
        "version": "0.1.0"
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "database": "connected" if checkpointer else "not configured",
        "timestamp": datetime.now().isoformat()
    }


async def format_stream_event(event_type: str, data: Any) -> str:
    """
    Format events in Vercel AI SDK Data Stream Protocol format.

    Format: {type}:{json_data}\n
    """
    payload = {
        "type": event_type,
        "data": data
    }
    return f"0:{json.dumps(payload)}\n"


def _normalize_search_mode(search_mode: SearchMode | Dict[str, Any] | str | None) -> Dict[str, Any]:
    if isinstance(search_mode, SearchMode):
        use_web = search_mode.useWebSearch
        use_agent = search_mode.useAgent
        use_deep = search_mode.useDeepSearch
    elif isinstance(search_mode, dict):
        use_web = bool(search_mode.get("useWebSearch"))
        use_agent = bool(search_mode.get("useAgent"))
        use_deep = bool(search_mode.get("useDeepSearch"))
    elif isinstance(search_mode, str):
        lowered = search_mode.lower()
        use_web = lowered in {"web", "search", "tavily"}
        use_agent = lowered in {"agent", "deep"}
        use_deep = lowered == "deep"
    else:
        use_web = False
        use_agent = False
        use_deep = False

    if use_deep and not use_agent:
        use_deep = False

    if use_agent:
        mode = "deep" if use_deep else "agent"
    elif use_web:
        mode = "web"
    else:
        mode = "direct"

    return {
        "use_web": use_web,
        "use_agent": use_agent,
        "use_deep": use_deep,
        "mode": mode,
    }


async def stream_agent_events(
    input_text: str,
    thread_id: str = "default",
    model: str = "gpt-4o",
    search_mode: Dict[str, Any] | None = None
):
    """
    Stream agent execution events in real-time.

    Converts LangGraph events to Vercel AI SDK format.
    """
    try:
        # Initialize state
        initial_state: AgentState = {
            "input": input_text,
            "messages": [],
            "research_plan": [],
            "current_step": 0,
            "scraped_content": [],
            "code_results": [],
            "final_report": "",
            "draft_report": "",
            "evaluation": "",
            "verdict": "",
            "route": "",
            "revision_count": 0,
            "max_revisions": settings.max_revisions,
            "is_complete": False,
            "errors": []
        }

        mode_info = _normalize_search_mode(search_mode)

        config = {
            "configurable": {
                "thread_id": thread_id,
                "model": model,
                "search_mode": mode_info,
                "allow_interrupts": bool(checkpointer),
                "tool_approval": settings.tool_approval or False,
                "human_review": settings.human_review or False,
                "max_revisions": settings.max_revisions
            },
            "recursion_limit": 50
        }

        # Send initial status
        yield await format_stream_event("status", {
            "text": "Initializing research agent...",
            "step": "init"
        })

        # Stream graph execution
        async for event in research_graph.astream_events(
            initial_state,
            config=config
        ):
            event_type = event.get("event")
            name = event.get("name", "") or event.get("run_name", "")
            data_dict = event.get("data", {})
            node_name = name.lower() if isinstance(name, str) else ""

            # Handle different event types
            if event_type in {"on_chain_start", "on_node_start", "on_graph_start"}:
                if "planner" in node_name:
                    yield await format_stream_event("status", {
                        "text": "Creating research plan...",
                        "step": "planning"
                    })
                elif "perform_parallel_search" in node_name or "search" in node_name:
                    yield await format_stream_event("status", {
                        "text": "Conducting research...",
                        "step": "researching"
                    })
                elif "writer" in node_name:
                    yield await format_stream_event("status", {
                        "text": "Synthesizing findings...",
                        "step": "writing"
                    })

            elif event_type in {"on_chain_end", "on_node_end", "on_graph_end"}:
                output = data_dict.get("output", {}) if isinstance(data_dict, dict) else {}

                # Extract messages from output
                if isinstance(output, dict):
                    # Interrupt handling
                    interrupts = output.get("__interrupt__")
                    if interrupts:
                        yield await format_stream_event("interrupt", {
                            "prompts": _serialize_interrupts(interrupts)
                        })
                        return

                    messages = output.get("messages", [])
                    if messages:
                        for msg in messages:
                            content = msg.content if hasattr(msg, 'content') else str(msg)
                            yield await format_stream_event("message", {
                                "content": content
                            })

                    # Check for completion and final report artifact
                    if output.get("is_complete"):
                        final_report = output.get("final_report", "")
                        if final_report:
                            yield await format_stream_event("completion", {
                                "content": final_report
                            })
                            
                            # Also emit as artifact
                            yield await format_stream_event("artifact", {
                                "id": f"report_{datetime.now().timestamp()}",
                                "type": "report",
                                "title": "Research Report",
                                "content": final_report
                            })

            elif event_type == "on_tool_start":
                tool_name = data_dict.get("name", "unknown")
                tool_input = data_dict.get("input", {})

                if "search" in tool_name.lower():
                    query = tool_input.get("query", "unknown")
                    yield await format_stream_event("tool", {
                        "name": "search",
                        "status": "running",
                        "query": query
                    })
                elif "code" in tool_name.lower():
                    yield await format_stream_event("tool", {
                        "name": "code_execution",
                        "status": "running"
                    })

            elif event_type == "on_tool_end":
                tool_name = data_dict.get("name", "unknown")
                output = data_dict.get("output", {})
                
                yield await format_stream_event("tool", {
                    "name": tool_name,
                    "status": "completed"
                })

                # Check for artifacts from code execution
                if tool_name == "execute_python_code" and isinstance(output, dict):
                    image_data = output.get("image")
                    
                    if image_data:
                        yield await format_stream_event("artifact", {
                            "id": f"art_{datetime.now().timestamp()}",
                            "type": "chart",
                            "title": "Generated Visualization",
                            "content": "Chart generated from Python code",
                            "image": image_data
                        })

            elif event_type in {"on_chat_model_stream", "on_llm_stream"}:
                # Stream LLM tokens
                chunk = data_dict.get("chunk") or data_dict.get("output")
                if chunk is not None:
                    content = None
                    if hasattr(chunk, "content"):
                        content = chunk.content
                    elif isinstance(chunk, dict):
                        content = chunk.get("content")
                    if content:
                        yield await format_stream_event("text", {"content": content})

        # Send final completion
        yield await format_stream_event("done", {
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Stream error: {str(e)}", exc_info=True)
        yield await format_stream_event("error", {
            "message": str(e)
        })


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Main chat endpoint with streaming support.

    Compatible with Vercel AI SDK useChat hook.
    """
    try:
        # Get the last user message
        user_messages = [msg for msg in request.messages if msg.role == "user"]
        if not user_messages:
            raise HTTPException(status_code=400, detail="No user message found")

        last_message = user_messages[-1].content

        mode_info = _normalize_search_mode(request.search_mode)
        logger.info(f"Processing chat request: {last_message[:100]}... Mode: {mode_info.get('mode')}")

        if request.stream:
            # Return streaming response
            return StreamingResponse(
                stream_agent_events(last_message, model=request.model, search_mode=mode_info),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # Non-streaming response (fallback)
            initial_state: AgentState = {
                "input": last_message,
                "messages": [],
                "research_plan": [],
                "current_step": 0,
                "scraped_content": [],
                "code_results": [],
                "final_report": "",
                "draft_report": "",
                "evaluation": "",
                "verdict": "",
                "route": mode_info.get("mode", "direct"),
                "revision_count": 0,
                "max_revisions": settings.max_revisions,
                "is_complete": False,
                "errors": []
            }

            config = {
                "configurable": {
                    "thread_id": "default",
                    "model": request.model,
                    "search_mode": mode_info,
                    "allow_interrupts": bool(checkpointer),
                    "tool_approval": settings.tool_approval or False,
                    "human_review": settings.human_review or False,
                    "max_revisions": settings.max_revisions,
                },
                "recursion_limit": 50,
            }
            result = await research_graph.ainvoke(initial_state, config=config)
            final_report = result.get("final_report", "No response generated")

            return ChatResponse(
                id=f"msg_{datetime.now().timestamp()}",
                content=final_report,
                timestamp=datetime.now().isoformat()
            )

    except Exception as e:
        logger.error(f"Chat error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/interrupt/resume")
async def resume_interrupt(request: ResumeRequest):
    """
    Resume a LangGraph execution after an interrupt.
    """
    if not checkpointer:
        raise HTTPException(status_code=400, detail="Interrupts require a checkpointer")

    mode_info = _normalize_search_mode(request.search_mode)
    config = {
        "configurable": {
            "thread_id": request.thread_id,
            "model": request.model,
            "search_mode": mode_info,
            "allow_interrupts": True,
            "tool_approval": settings.tool_approval or False,
            "human_review": settings.human_review or False,
            "max_revisions": settings.max_revisions,
        },
        "recursion_limit": 50,
    }

    result = await research_graph.ainvoke(Command(resume=request.payload), config=config)
    interrupts = _serialize_interrupts(result.get("__interrupt__"))
    if interrupts:
        return {"status": "interrupted", "interrupts": interrupts}

    final_report = result.get("final_report", "")
    return ChatResponse(
        id=f"msg_{datetime.now().timestamp()}",
        content=final_report,
        timestamp=datetime.now().isoformat()
    )


@app.post("/api/research")
async def research(query: str):
    """
    Dedicated research endpoint for long-running queries.

    Returns streaming response with research progress.
    """
    return StreamingResponse(
        stream_agent_events(query),
        media_type="text/event-stream"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
