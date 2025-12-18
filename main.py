from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import base64
from pydantic import BaseModel
from langchain_core.messages import SystemMessage, HumanMessage
from typing import List, Dict, Any, Optional
import json
import asyncio
import uuid
from datetime import datetime
from pathlib import Path
import time
import logging

from common.config import settings
from langgraph.types import Command
from langgraph.checkpoint.memory import InMemorySaver
from agent import create_research_graph, create_checkpointer, AgentState
from agent.deep_agent import get_deep_agent_prompt
from support_agent import create_support_graph
from tools.mcp import init_mcp_tools, close_mcp_tools, reload_mcp_tools
from tools.registry import set_registered_tools
from tools.memory_client import fetch_memories, add_memory_entry, store_interaction
from tools.asr import get_asr_service, init_asr_service
from common.logger import setup_logging, get_logger, LogContext
from common.cancellation import cancellation_manager

# Initialize logging
setup_logging()
logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Manus Research Agent API",
    description="Deep research AI agent with code execution capabilities",
    version="0.1.0"
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing information."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    logger.info(
        f"→ Request started | {request.method} {request.url.path} | "
        f"ID: {request_id} | Client: {request.client.host if request.client else 'unknown'}"
    )

    try:
        response = await call_next(request)
        duration = time.time() - start_time

        logger.info(
            f"← Request completed | {request.method} {request.url.path} | "
            f"ID: {request_id} | Status: {response.status_code} | "
            f"Duration: {duration:.3f}s"
        )

        return response
    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            f"✗ Request failed | {request.method} {request.url.path} | "
            f"ID: {request_id} | Duration: {duration:.3f}s | Error: {str(e)}",
            exc_info=True
        )
        raise


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize agent graphs with short-term memory (checkpointer)
if settings.database_url:
    checkpointer = create_checkpointer(settings.database_url)
else:
    # Fallback to in-memory checkpointer for short-term memory
    checkpointer = InMemorySaver()

research_graph = create_research_graph(
    checkpointer=checkpointer,
    interrupt_before=settings.interrupt_nodes_list
)
support_graph = create_support_graph(checkpointer=checkpointer)
mcp_enabled = settings.enable_mcp
mcp_servers_config = settings.mcp_servers
mcp_loaded_tools = 0


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    logger.info("=" * 80)
    logger.info("🚀 Weaver Research Agent Starting...")
    logger.info("=" * 80)

    # Log configuration
    logger.info(f"Environment: {'DEBUG' if settings.debug else 'PRODUCTION'}")
    logger.info(f"Primary Model: {settings.primary_model}")
    logger.info(f"Reasoning Model: {settings.reasoning_model}")
    logger.info(f"Database: {'Configured' if settings.database_url else 'Not configured'}")
    logger.info(f"Checkpointer: {'Enabled' if checkpointer else 'Disabled'}")

    # Initialize MCP tools
    global mcp_loaded_tools
    try:
        logger.info("Initializing MCP tools...")
        mcp_tools = await init_mcp_tools(servers_override=mcp_servers_config, enabled=mcp_enabled)
        if mcp_tools:
            set_registered_tools(mcp_tools)
            mcp_loaded_tools = len(mcp_tools)
            logger.info(f"✓ Successfully registered {mcp_loaded_tools} MCP tools")
        else:
            logger.info("No MCP tools to register")
            mcp_loaded_tools = 0
    except Exception as e:
        logger.warning(f"⚠ MCP tools initialization failed: {e}", exc_info=settings.debug)
        mcp_loaded_tools = 0

    # Initialize ASR service
    if settings.dashscope_api_key:
        try:
            logger.info("Initializing ASR service...")
            init_asr_service(settings.dashscope_api_key)
            logger.info("✓ ASR service initialized")
        except Exception as e:
            logger.warning(f"⚠ ASR service initialization failed: {e}")
    else:
        logger.info("ASR service not configured (no DASHSCOPE_API_KEY)")

    logger.info("=" * 80)
    logger.info("✓ Weaver Research Agent Ready")
    logger.info("=" * 80)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown."""
    logger.info("=" * 80)
    logger.info("🛑 Weaver Research Agent Shutting Down...")
    logger.info("=" * 80)

    try:
        logger.info("Closing MCP tools...")
        await close_mcp_tools()
        logger.info("✓ MCP tools closed successfully")
    except Exception as e:
        logger.error(f"✗ Error closing MCP tools: {e}", exc_info=True)

    logger.info("=" * 80)
    logger.info("✓ Shutdown Complete")
    logger.info("=" * 80)


# Request/Response models
class Message(BaseModel):
    role: str
    content: str


class SearchMode(BaseModel):
    useWebSearch: bool = False
    useAgent: bool = False
    useDeepSearch: bool = False


class ImagePayload(BaseModel):
    name: Optional[str] = None
    data: str
    mime: Optional[str] = None


class ChatRequest(BaseModel):
    messages: List[Message]
    stream: bool = True
    model: Optional[str] = "gpt-4o"
    search_mode: Optional[SearchMode | Dict[str, Any] | str] = None  # {"useWebSearch": bool, "useAgent": bool, "useDeepSearch": bool}
    images: Optional[List[ImagePayload]] = None  # Base64 images for multimodal input


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


class MCPConfigPayload(BaseModel):
    enable: Optional[bool] = None
    servers: Optional[Dict[str, Any]] = None


class SupportChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = "default_user"
    stream: bool = False  # reserved for future


class SupportChatResponse(BaseModel):
    content: str
    role: str = "assistant"
    timestamp: str


class CancelRequest(BaseModel):
    """取消任务请求"""
    reason: Optional[str] = "User requested cancellation"


# 存储活跃的流式任务
active_streams: Dict[str, asyncio.Task] = {}


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


# ==================== 取消任务 API ====================

@app.post("/api/chat/cancel/{thread_id}")
async def cancel_chat(thread_id: str, request: CancelRequest = None):
    """
    取消正在进行的聊天任务

    Args:
        thread_id: 任务线程 ID
        request: 可选的取消原因
    """
    reason = request.reason if request else "User requested cancellation"
    logger.info(f"Cancel request received for thread: {thread_id}, reason: {reason}")

    # 1. 通过 cancellation_manager 取消令牌
    cancelled = await cancellation_manager.cancel(thread_id, reason)

    # 2. 取消对应的异步任务（如果存在）
    if thread_id in active_streams:
        task = active_streams[thread_id]
        task.cancel()
        del active_streams[thread_id]
        logger.info(f"Async task for {thread_id} cancelled")

    if cancelled:
        return {
            "status": "cancelled",
            "thread_id": thread_id,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }
    else:
        return {
            "status": "not_found",
            "thread_id": thread_id,
            "message": "Task not found or already completed"
        }


@app.post("/api/chat/cancel-all")
async def cancel_all_chats():
    """取消所有正在进行的任务"""
    logger.info("Cancel all tasks requested")

    # 取消所有令牌
    await cancellation_manager.cancel_all("Batch cancellation requested")

    # 取消所有异步任务
    cancelled_count = len(active_streams)
    for task in active_streams.values():
        task.cancel()
    active_streams.clear()

    return {
        "status": "all_cancelled",
        "cancelled_count": cancelled_count,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/tasks/active")
async def get_active_tasks():
    """获取所有活跃任务列表"""
    active_tasks = cancellation_manager.get_active_tasks()
    stats = cancellation_manager.get_stats()

    return {
        "active_tasks": active_tasks,
        "stats": stats,
        "stream_count": len(active_streams),
        "timestamp": datetime.now().isoformat()
    }


# ==================== 流式事件格式化 ====================


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
        use_agent = lowered in {"agent", "deep", "deep_agent", "deep-agent"}
        use_deep = lowered in {"deep", "deep_agent", "deep-agent"}
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
        "use_deep_prompt": use_deep,
    }


def _normalize_images_payload(images: Optional[List[ImagePayload]]) -> List[Dict[str, Any]]:
    """
    Normalize incoming image payloads; strip data URL prefix if present.
    """
    normalized: List[Dict[str, Any]] = []
    if not images:
        return normalized

    for img in images:
        if not img or not img.data:
            continue
        data = img.data
        if data.startswith("data:") and "," in data:
            data = data.split(",", 1)[1]
        normalized.append({
            "name": img.name or "",
            "mime": img.mime or "",
            "data": data
        })
    return normalized


@app.post("/api/support/chat")
async def support_chat(request: SupportChatRequest):
    """Simple customer support chat backed by Mem0 memory."""
    try:
        state = {
            "messages": [SystemMessage(content="You are a helpful support assistant."), HumanMessage(content=request.message)],
            "user_id": request.user_id or "default_user",
        }
        config = {"configurable": {"thread_id": request.user_id or "support_default"}}
        result = support_graph.invoke(state, config=config)
        messages = result.get("messages", [])
        reply = ""
        for msg in reversed(messages):
            if hasattr(msg, "content"):
                reply = msg.content
                break
        if not reply:
            reply = "No response generated."
        return SupportChatResponse(
            content=reply,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Support chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def stream_agent_events(
    input_text: str,
    thread_id: str = "default",
    model: str = "gpt-4o",
    search_mode: Dict[str, Any] | None = None,
    images: Optional[List[Dict[str, Any]]] = None
):
    """
    Stream agent execution events in real-time.

    Converts LangGraph events to Vercel AI SDK format.
    Supports cancellation via cancellation_manager.
    """
    event_count = 0
    start_time = time.time()
    images = images or []

    # Optional per-thread log handler for easier debugging
    thread_handler = None
    root_logger = logging.getLogger()
    if settings.enable_file_logging:
        try:
            log_path = Path(settings.log_file)
            thread_log_dir = log_path.parent / "threads"
            thread_log_dir.mkdir(parents=True, exist_ok=True)
            thread_log_file = thread_log_dir / f"{thread_id}.log"

            # Reuse formatter from existing handlers if available
            formatter = None
            if root_logger.handlers:
                formatter = root_logger.handlers[0].formatter
            thread_handler = logging.FileHandler(thread_log_file, encoding="utf-8")
            if formatter:
                thread_handler.setFormatter(formatter)
            thread_handler.setLevel(root_logger.level)
            root_logger.addHandler(thread_handler)
            logger.info(f"Thread log file attached: {thread_log_file}")
        except Exception as e:
            logger.warning(f"Failed to attach thread log handler: {e}")

    # 创建取消令牌
    cancel_token = await cancellation_manager.create_token(
        thread_id,
        metadata={"model": model, "input_preview": input_text[:100]}
    )

    try:
        logger.info(f"🎯 Agent stream started | Thread: {thread_id} | Model: {model}")
        logger.debug(f"  Input: {input_text[:100]}...")

        mode_info = _normalize_search_mode(search_mode)

        # Initialize state with cancellation support
        initial_state: AgentState = {
            "input": input_text,
            "images": images,
            "needs_clarification": False,
            "tool_approved": False,
            "pending_tool_calls": [],
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
            "errors": [],
            # 取消控制字段
            "cancel_token_id": thread_id,
            "is_cancelled": False
        }

        # Load long-term memories (optional) and inject deep prompt if needed
        messages: list[Any] = []
        if mode_info.get("use_deep_prompt"):
            messages.append(SystemMessage(content=get_deep_agent_prompt()))

        mem_entries = fetch_memories(query=input_text)
        if mem_entries:
            memory_text = "\n".join(f"- {m}" for m in mem_entries)
            messages.append(SystemMessage(content=f"Relevant past knowledge:\n{memory_text}"))

        if messages:
            initial_state["messages"] = messages

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
            "step": "init",
            "thread_id": thread_id
        })

        # Stream graph execution
        async for event in research_graph.astream_events(
            initial_state,
            config=config
        ):
            # 检查取消状态
            if cancel_token.is_cancelled:
                logger.info(f"Stream cancelled for thread {thread_id}")
                yield await format_stream_event("cancelled", {
                    "message": "Task was cancelled by user",
                    "thread_id": thread_id
                })
                return

            event_type = event.get("event")
            name = event.get("name", "") or event.get("run_name", "")
            data_dict = event.get("data", {})
            node_name = name.lower() if isinstance(name, str) else ""

            # Handle different event types
            if event_type in {"on_chain_start", "on_node_start", "on_graph_start"}:
                event_count += 1
                if "clarify" in node_name:
                    logger.debug(f"  ❓ Clarify node started | Thread: {thread_id}")
                    yield await format_stream_event("status", {
                        "text": "Checking if clarification is needed...",
                        "step": "clarifying"
                    })
                elif "planner" in node_name:
                    logger.debug(f"  📋 Planning node started | Thread: {thread_id}")
                    yield await format_stream_event("status", {
                        "text": "Creating research plan...",
                        "step": "planning"
                    })
                elif "perform_parallel_search" in node_name or "search" in node_name:
                    logger.debug(f"  🔍 Search node started | Thread: {thread_id}")
                    yield await format_stream_event("status", {
                        "text": "Conducting research...",
                        "step": "researching"
                    })
                elif "writer" in node_name:
                    logger.debug(f"  ✍️  Writer node started | Thread: {thread_id}")
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
                            "thread_id": thread_id,
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
                            # Store memory for future sessions
                            # Store memory (long-term)
                            add_memory_entry(final_report)
                            # Store interaction (question + answer)
                            store_interaction(input_text, final_report)

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
        duration = time.time() - start_time
        cancel_token.mark_completed()
        logger.info(
            f"✓ Agent stream completed | Thread: {thread_id} | "
            f"Events: {event_count} | Duration: {duration:.2f}s"
        )
        yield await format_stream_event("done", {
            "timestamp": datetime.now().isoformat()
        })

    except asyncio.CancelledError:
        duration = time.time() - start_time
        logger.info(
            f"⊘ Agent stream cancelled | Thread: {thread_id} | "
            f"Duration: {duration:.2f}s"
        )
        yield await format_stream_event("cancelled", {
            "message": "Task was cancelled",
            "thread_id": thread_id,
            "duration": duration
        })

    except Exception as e:
        duration = time.time() - start_time
        cancel_token.mark_failed(str(e))
        logger.error(
            f"✗ Agent stream error | Thread: {thread_id} | "
            f"Duration: {duration:.2f}s | Error: {str(e)}",
            exc_info=True
        )
        yield await format_stream_event("error", {
            "message": str(e)
        })

    finally:
        # 清理活跃流记录
        if thread_id in active_streams:
            del active_streams[thread_id]
        if thread_handler:
            try:
                root_logger.removeHandler(thread_handler)
                thread_handler.close()
            except Exception:
                pass


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Main chat endpoint with streaming support.

    Compatible with Vercel AI SDK useChat hook.
    """
    thread_id = None
    try:
        # Get the last user message
        user_messages = [msg for msg in request.messages if msg.role == "user"]
        if not user_messages:
            logger.warning("Chat request received with no user messages")
            raise HTTPException(status_code=400, detail="No user message found")

        last_message = user_messages[-1].content
        mode_info = _normalize_search_mode(request.search_mode)

        logger.info(f"📨 Chat request received")
        logger.info(f"  Model: {request.model}")
        logger.info(f"  Mode: {mode_info.get('mode')}")
        logger.info(f"  Stream: {request.stream}")
        logger.info(f"  Message length: {len(last_message)} chars")
        logger.debug(f"  Message preview: {last_message[:200]}...")

        if request.stream:
            thread_id = f"thread_{uuid.uuid4().hex}"
            logger.info(f"🌊 Starting streaming response | Thread: {thread_id}")

            # Return streaming response with thread_id in header for cancellation
            return StreamingResponse(
                stream_agent_events(
                    last_message,
                    thread_id=thread_id,
                    model=request.model,
                    search_mode=mode_info,
                    images=_normalize_images_payload(request.images)
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Thread-ID": thread_id  # 供前端用于取消请求
                }
            )
        else:
            # Non-streaming response (fallback)
            initial_state: AgentState = {
                "input": last_message,
                "images": _normalize_images_payload(request.images),
                "needs_clarification": False,
                "tool_approved": False,
                "pending_tool_calls": [],
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

            messages: list[Any] = []
            if mode_info.get("use_deep_prompt"):
                messages.append(SystemMessage(content=get_deep_agent_prompt()))

            mem_entries = fetch_memories(query=last_message)
            if mem_entries:
                memory_text = "\n".join(f"- {m}" for m in mem_entries)
                messages.append(SystemMessage(content=f"Relevant past knowledge:\n{memory_text}"))

            if messages:
                initial_state["messages"] = messages

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
            add_memory_entry(final_report)
            store_interaction(last_message, final_report)

            return ChatResponse(
                id=f"msg_{datetime.now().timestamp()}",
                content=final_report,
                timestamp=datetime.now().isoformat()
            )

    except Exception as e:
        logger.error(
            f"✗ Chat error | Thread: {thread_id or 'N/A'} | "
            f"Model: {request.model if 'request' in locals() else 'N/A'} | "
            f"Error: {str(e)}",
            exc_info=True
        )
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


@app.get("/api/mcp/config")
async def get_mcp_config():
    """Return current MCP enable flag, servers config, and loaded tool count."""
    return {
        "enabled": mcp_enabled,
        "servers": mcp_servers_config,
        "loaded_tools": mcp_loaded_tools,
    }


@app.post("/api/mcp/config")
async def update_mcp_config(payload: MCPConfigPayload):
    """Update MCP enable flag and servers config at runtime."""
    global mcp_enabled, mcp_servers_config, mcp_loaded_tools

    if payload.enable is not None:
        mcp_enabled = bool(payload.enable)
    if payload.servers is not None:
        mcp_servers_config = payload.servers

    if mcp_enabled and mcp_servers_config:
        try:
            tools = await reload_mcp_tools(mcp_servers_config, enabled=True)
            set_registered_tools(tools)
            mcp_loaded_tools = len(tools)
        except Exception as e:
            logger.error(f"Failed to reload MCP tools: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to reload MCP tools")
    else:
        await close_mcp_tools()
        set_registered_tools([])
        mcp_loaded_tools = 0

    return {
        "enabled": mcp_enabled,
        "servers": mcp_servers_config,
        "loaded_tools": mcp_loaded_tools,
    }


# ==================== ASR 语音识别 API ====================

class ASRRequest(BaseModel):
    """ASR 请求 - Base64 编码的音频数据"""
    audio_data: str  # Base64 encoded audio
    format: str = "wav"
    sample_rate: int = 16000
    language_hints: Optional[List[str]] = None


@app.post("/api/asr/recognize")
async def recognize_speech(request: ASRRequest):
    """
    语音识别端点 - 接收 Base64 编码的音频数据

    Args:
        request: ASR 请求，包含 Base64 编码的音频数据

    Returns:
        识别结果
    """
    try:
        asr_service = get_asr_service()

        if not asr_service.enabled:
            raise HTTPException(
                status_code=503,
                detail="ASR service not available. Please configure DASHSCOPE_API_KEY."
            )

        # 解码 Base64 音频数据
        try:
            audio_bytes = base64.b64decode(request.audio_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64 audio data: {str(e)}")

        # 调用 ASR 服务
        result = asr_service.recognize_bytes(
            audio_data=audio_bytes,
            format=request.format,
            sample_rate=request.sample_rate,
            language_hints=request.language_hints or ['zh', 'en']
        )

        if result["success"]:
            return {
                "success": True,
                "text": result["text"],
                "metrics": result.get("metrics", {})
            }
        else:
            return {
                "success": False,
                "text": "",
                "error": result.get("error", "Unknown error")
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ASR error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"ASR processing error: {str(e)}")


@app.post("/api/asr/upload")
async def recognize_speech_upload(
    file: UploadFile = File(...),
    sample_rate: int = 16000
):
    """
    语音识别端点 - 接收上传的音频文件

    Args:
        file: 上传的音频文件
        sample_rate: 采样率

    Returns:
        识别结果
    """
    try:
        asr_service = get_asr_service()

        if not asr_service.enabled:
            raise HTTPException(
                status_code=503,
                detail="ASR service not available. Please configure DASHSCOPE_API_KEY."
            )

        # 读取文件内容
        audio_bytes = await file.read()

        # 根据文件扩展名确定格式
        filename = file.filename or "audio.wav"
        format_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"

        # 调用 ASR 服务
        result = asr_service.recognize_bytes(
            audio_data=audio_bytes,
            format=format_ext,
            sample_rate=sample_rate,
            language_hints=['zh', 'en']
        )

        if result["success"]:
            return {
                "success": True,
                "text": result["text"],
                "metrics": result.get("metrics", {})
            }
        else:
            return {
                "success": False,
                "text": "",
                "error": result.get("error", "Unknown error")
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ASR upload error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"ASR processing error: {str(e)}")


@app.get("/api/asr/status")
async def get_asr_status():
    """获取 ASR 服务状态"""
    asr_service = get_asr_service()
    return {
        "enabled": asr_service.enabled,
        "api_key_configured": bool(settings.dashscope_api_key)
    }


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
