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
from langgraph.store.memory import InMemoryStore
from agent import create_research_graph, create_checkpointer, AgentState
from agent.deep_agent import get_deep_agent_prompt
from support_agent import create_support_graph
from tools.mcp import init_mcp_tools, close_mcp_tools, reload_mcp_tools
from tools.registry import set_registered_tools
from tools.memory_client import fetch_memories, add_memory_entry, store_interaction
from tools.asr import get_asr_service, init_asr_service
from tools.tts import get_tts_service, init_tts_service, AVAILABLE_VOICES
from common.logger import setup_logging, get_logger, LogContext
from common.metrics import metrics_registry
from common.cancellation import cancellation_manager
try:
    from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
except ImportError:  # optional
    Counter = Gauge = generate_latest = CONTENT_TYPE_LATEST = None
try:
    from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
except ImportError:
    Counter = Gauge = generate_latest = CONTENT_TYPE_LATEST = None

# Initialize logging
setup_logging()
logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Manus Research Agent API",
    description="Deep research AI agent with code execution capabilities",
    version="0.1.0"
)

# Prometheus metrics (optional)
http_requests_total = Counter("weaver_http_requests_total", "Total HTTP requests", ["method", "path", "status"]) if Counter else None
http_inprogress = Gauge("weaver_http_inprogress", "In-flight HTTP requests") if Gauge else None

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing information."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    if http_inprogress:
        http_inprogress.inc()

    logger.info(
        f"? Request started | {request.method} {request.url.path} | "
        f"ID: {request_id} | Client: {request.client.host if request.client else 'unknown'}"
    )

    try:
        response = await call_next(request)
        duration = time.time() - start_time

        logger.info(
            f"? Request completed | {request.method} {request.url.path} | "
            f"ID: {request_id} | Status: {response.status_code} | "
            f"Duration: {duration:.3f}s"
        )
        if http_requests_total:
            http_requests_total.labels(request.method, request.url.path, response.status_code).inc()

        return response
    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            f"? Request failed | {request.method} {request.url.path} | "
            f"ID: {request_id} | Duration: {duration:.3f}s | Error: {str(e)}",
            exc_info=True
        )
        if http_requests_total:
            http_requests_total.labels(request.method, request.url.path, 500).inc()
        raise
    finally:
        if http_inprogress:
            http_inprogress.dec()

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

def _init_store():
    backend = settings.memory_store_backend.lower().strip()
    url = settings.memory_store_url.strip()
    if backend == "postgres" and url:
        try:
            from langgraph.store.postgres import PostgresStore
            store_obj = PostgresStore.from_conn_string(url)
            store_obj.setup()
            logger.info("Initialized PostgresStore for long-term memory")
            return store_obj
        except Exception as e:
            logger.warning(f"Failed to init PostgresStore, falling back to in-memory. Error: {e}")
    if backend == "redis" and url:
        try:
            from langgraph.store.redis import RedisStore
            store_obj = RedisStore.from_conn_string(url)
            store_obj.setup()
            logger.info("Initialized RedisStore for long-term memory")
            return store_obj
        except Exception as e:
            logger.warning(f"Failed to init RedisStore, falling back to in-memory. Error: {e}")

    logger.info("Using InMemoryStore for long-term memory")
    return InMemoryStore()

# Long-term memory store (configurable via .env)
store = _init_store()

research_graph = create_research_graph(
    checkpointer=checkpointer,
    interrupt_before=settings.interrupt_nodes_list,
    store=store,
)
support_graph = create_support_graph(checkpointer=checkpointer, store=store)
mcp_enabled = settings.enable_mcp
mcp_servers_config = settings.mcp_servers
mcp_loaded_tools = 0


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    logger.info("=" * 80)
    logger.info("馃殌 Weaver Research Agent Starting...")
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
            logger.info(f"鉁?Successfully registered {mcp_loaded_tools} MCP tools")
        else:
            logger.info("No MCP tools to register")
            mcp_loaded_tools = 0
    except Exception as e:
        logger.warning(f"鈿?MCP tools initialization failed: {e}", exc_info=settings.debug)
        mcp_loaded_tools = 0

    # Initialize ASR service
    if settings.dashscope_api_key:
        try:
            logger.info("Initializing ASR service...")
            init_asr_service(settings.dashscope_api_key)
            logger.info("鉁?ASR service initialized")
        except Exception as e:
            logger.warning(f"鈿?ASR service initialization failed: {e}")
    else:
        logger.info("ASR service not configured (no DASHSCOPE_API_KEY)")

    # Initialize TTS service
    if settings.dashscope_api_key:
        try:
            logger.info("Initializing TTS service...")
            init_tts_service(settings.dashscope_api_key)
            logger.info("鉁?TTS service initialized")
        except Exception as e:
            logger.warning(f"鈿?TTS service initialization failed: {e}")
    else:
        logger.info("TTS service not configured (no DASHSCOPE_API_KEY)")

    logger.info("=" * 80)
    logger.info("鉁?Weaver Research Agent Ready")
    logger.info("=" * 80)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown."""
    logger.info("=" * 80)
    logger.info("馃洃 Weaver Research Agent Shutting Down...")
    logger.info("=" * 80)

    try:
        logger.info("Closing MCP tools...")
        await close_mcp_tools()
        logger.info("鉁?MCP tools closed successfully")
    except Exception as e:
        logger.error(f"鉁?Error closing MCP tools: {e}", exc_info=True)

    logger.info("=" * 80)
    logger.info("鉁?Shutdown Complete")
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
    user_id: Optional[str] = None
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
    """鍙栨秷浠诲姟璇锋眰"""
    reason: Optional[str] = "User requested cancellation"


# 瀛樺偍娲昏穬鐨勬祦寮忎换鍔?active_streams: Dict[str, asyncio.Task] = {}


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


# ==================== 鍙栨秷浠诲姟 API ====================

@app.post("/api/chat/cancel/{thread_id}")
async def cancel_chat(thread_id: str, request: CancelRequest = None):
    """
    鍙栨秷姝ｅ湪杩涜鐨勮亰澶╀换鍔?
    Args:
        thread_id: 浠诲姟绾跨▼ ID
        request: 鍙€夌殑鍙栨秷鍘熷洜
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
    """鍙栨秷鎵€鏈夋鍦ㄨ繘琛岀殑浠诲姟"""
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
    """Get all active tasks."""
    active_tasks = cancellation_manager.get_active_tasks()

    return {
        "active_tasks": active_tasks,
        "stats": stats,
        "stream_count": len(active_streams),
        "timestamp": datetime.now().isoformat()
    }


# ==================== 娴佸紡浜嬩欢鏍煎紡鍖?====================


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
        lowered = search_mode.lower().strip()

        # UX labels
        if lowered in {"direct", ""}:
            use_web = False
            use_agent = False
            use_deep = False
        else:
            use_web = lowered in {"web", "search", "tavily"}
            use_agent = lowered in {"agent", "deep", "deep_agent", "deep-agent", "ultra"}
            use_deep = lowered in {"deep", "deep_agent", "deep-agent", "ultra"}
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


def _store_search(query: str, user_id: str, limit: int = 3) -> List[str]:
    if not store:
        return []
    namespace = (user_id, "memories")
    try:
        results = store.search(namespace, query=query or "", limit=limit)
        texts: List[str] = []
        for item in results:
            value = getattr(item, "value", {}) or {}
            if isinstance(value, dict):
                text = value.get("content") or value.get("text") or value.get("data")
                if text:
                    texts.append(str(text))
            elif isinstance(value, str):
                texts.append(value)
        return texts[:limit]
    except Exception as e:
        logger.debug(f"Store search failed: {e}")
        return []


def _store_add(query: str, content: str, user_id: str):
    if not store or not content:
        return
    namespace = (user_id, "memories")
    try:
        key = f"mem_{uuid.uuid4().hex}"
        store.put(namespace, key, {"query": query, "content": content})
    except Exception as e:
        logger.debug(f"Store add failed: {e}")


@app.post("/api/support/chat")
async def support_chat(request: SupportChatRequest):
    """Simple customer support chat backed by Mem0 memory."""
    try:
        state = {
            "messages": [SystemMessage(content="You are a helpful support assistant."), HumanMessage(content=request.message)],
            "user_id": request.user_id or "default_user",
        }
        config = {"configurable": {"thread_id": request.user_id or "support_default"}}
        # Inject stored memories if present
        store_memories = _store_search(request.message, user_id=state["user_id"])
        if store_memories:
            state["messages"].insert(0, SystemMessage(content="Stored memories:\n" + "\n".join(f"- {m}" for m in store_memories)))

        result = support_graph.invoke(state, config=config)
        messages = result.get("messages", [])
        reply = ""
        for msg in reversed(messages):
            if hasattr(msg, "content"):
                reply = msg.content
                break
        if not reply:
            reply = "No response generated."
        _store_add(request.message, reply, user_id=state["user_id"])
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
    images: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[str] = None
):
    """
    Stream agent execution events in real-time.

    Converts LangGraph events to Vercel AI SDK format.
    Supports cancellation via cancellation_manager.
    """
    event_count = 0
    start_time = time.time()
    images = images or []
    user_id = user_id or settings.memory_user_id

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

    # 鍒涘缓鍙栨秷浠ょ墝
    cancel_token = await cancellation_manager.create_token(
        thread_id,
        metadata={"model": model, "input_preview": input_text[:100]}
    )

    try:
        logger.info(f"馃幆 Agent stream started | Thread: {thread_id} | Model: {model}")
        logger.debug(f"  Input: {input_text[:100]}...")

        mode_info = _normalize_search_mode(search_mode)
        metrics = metrics_registry.start(thread_id, model=model, route=mode_info.get("mode", ""))

        # Initialize state with cancellation support
        initial_state: AgentState = {
            "input": input_text,
            "images": images,
            "needs_clarification": False,
            "tool_approved": False,
            "pending_tool_calls": [],
            "user_id": user_id,
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
            "tool_call_count": 0,
            "is_complete": False,
            "errors": [],
            # 鍙栨秷鎺у埗瀛楁
            "cancel_token_id": thread_id,
            "is_cancelled": False
        }

        # Load long-term memories (store) and Mem0 (optional) and inject deep prompt if needed
        messages: list[Any] = []
        if mode_info.get("use_deep_prompt"):
            messages.append(SystemMessage(content=get_deep_agent_prompt()))

        store_memories = _store_search(input_text, user_id=user_id)
        if store_memories:
            store_text = "\n".join(f"- {m}" for m in store_memories)
            messages.append(SystemMessage(content=f"Stored memories:\n{store_text}"))

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
                "user_id": user_id,
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
            # Check cancellation status
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
                metrics.mark_event(event_type, node_name)
                if "clarify" in node_name:
                    logger.debug(f"  鉂?Clarify node started | Thread: {thread_id}")
                    yield await format_stream_event("status", {
                        "text": "Checking if clarification is needed...",
                        "step": "clarifying"
                    })
                elif "planner" in node_name:
                    logger.debug(f"  馃搵 Planning node started | Thread: {thread_id}")
                    yield await format_stream_event("status", {
                        "text": "Creating research plan...",
                        "step": "planning"
                    })
                elif "perform_parallel_search" in node_name or "search" in node_name:
                    logger.debug(f"  馃攳 Search node started | Thread: {thread_id}")
                    yield await format_stream_event("status", {
                        "text": "Conducting research...",
                        "step": "researching"
                    })
                elif "writer" in node_name:
                    logger.debug(f"  鉁嶏笍  Writer node started | Thread: {thread_id}")
                    yield await format_stream_event("status", {
                        "text": "Synthesizing findings...",
                        "step": "writing"
                    })

            elif event_type in {"on_chain_end", "on_node_end", "on_graph_end"}:
                output = data_dict.get("output", {}) if isinstance(data_dict, dict) else {}
                metrics.mark_event(event_type, node_name)

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
                            # Store to graph store
                            _store_add(input_text, final_report, user_id=user_id)

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
        metrics_registry.finish(thread_id, cancelled=False)
        logger.info(
            f"вњ?Agent stream completed | Thread: {thread_id} | "
            f"Events: {event_count} | Duration: {duration:.2f}s"
        )
        yield await format_stream_event("done", {
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics_registry.get(thread_id).to_dict() if metrics_registry.get(thread_id) else {}
        })

    except asyncio.CancelledError:
        duration = time.time() - start_time
        metrics_registry.finish(thread_id, cancelled=True)
        logger.info(
            f"? Agent stream cancelled | Thread: {thread_id} | "
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
        metrics_registry.finish(thread_id, cancelled=False)
        logger.error(
            f"? Agent stream error | Thread: {thread_id} | "
            f"Duration: {duration:.2f}s | Error: {str(e)}",
            exc_info=True
        )
        yield await format_stream_event("error", {
            "message": str(e)
        })

    finally:
        # ???????
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
        user_id = request.user_id or settings.memory_user_id
        mode_info = _normalize_search_mode(request.search_mode)

        logger.info(f"馃摠 Chat request received")
        logger.info(f"  Model: {request.model}")
        logger.info(f"  Mode: {mode_info.get('mode')}")
        logger.info(f"  Stream: {request.stream}")
        logger.info(f"  Message length: {len(last_message)} chars")
        logger.debug(f"  Message preview: {last_message[:200]}...")

        if request.stream:
            thread_id = f"thread_{uuid.uuid4().hex}"
            logger.info(f"馃寠 Starting streaming response | Thread: {thread_id}")

            # Return streaming response with thread_id in header for cancellation
            return StreamingResponse(
                stream_agent_events(
                    last_message,
                    thread_id=thread_id,
                    model=request.model,
                    search_mode=mode_info,
                    images=_normalize_images_payload(request.images),
                    user_id=user_id
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Thread-ID": thread_id  # ?????????
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
                "user_id": user_id,
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

            store_memories = _store_search(last_message, user_id=user_id)
            if store_memories:
                store_text = "\n".join(f"- {m}" for m in store_memories)
                messages.append(SystemMessage(content=f"Stored memories:\n{store_text}"))

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
                    "user_id": user_id,
                    "allow_interrupts": bool(checkpointer),
                    "tool_approval": settings.tool_approval or False,
                    "human_review": settings.human_review or False,
                    "max_revisions": settings.max_revisions,
                },
                "recursion_limit": 50,
            }
            thread_id = thread_id or f"thread_{uuid.uuid4().hex}"
            metrics = metrics_registry.start(thread_id, model=request.model, route=mode_info.get("mode", "direct"))
            result = await research_graph.ainvoke(initial_state, config=config)
            final_report = result.get("final_report", "No response generated")
            add_memory_entry(final_report)
            store_interaction(last_message, final_report)
            _store_add(last_message, final_report, user_id=user_id)
            metrics_registry.finish(thread_id, cancelled=False)

            return ChatResponse(
                id=f"msg_{datetime.now().timestamp()}",
                content=final_report,
                timestamp=datetime.now().isoformat()
            )

    except Exception as e:
        logger.error(
            f"鉁?Chat error | Thread: {thread_id or 'N/A'} | "
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




@app.get("/api/runs")
async def list_runs():
    """List in-memory run metrics (per thread)."""
    return {"runs": metrics_registry.all()}


@app.get("/api/runs/{thread_id}")
async def get_run_metrics(thread_id: str):
    """Get metrics for a specific run/thread."""
    metrics = metrics_registry.get(thread_id)
    if not metrics:
        raise HTTPException(status_code=404, detail="Run not found")
    return metrics.to_dict()



@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint (enable with ENABLE_PROMETHEUS=true)."""
    if not settings.enable_prometheus or not generate_latest:
        raise HTTPException(status_code=404, detail="Prometheus not enabled")
    data = generate_latest()
    return StreamingResponse(iter([data]), media_type=CONTENT_TYPE_LATEST)

# ==================== ASR 璇煶璇嗗埆 API ====================

class ASRRequest(BaseModel):
    """ASR request with base64 audio data."""
    audio_data: str  # Base64 encoded audio
    format: str = "wav"
    sample_rate: int = 16000
    language_hints: Optional[List[str]] = None


@app.post("/api/asr/recognize")
async def recognize_speech(request: ASRRequest):
    """ASR endpoint receiving Base64 audio data."""
    try:
        asr_service = get_asr_service()

        if not asr_service.enabled:
            raise HTTPException(
                status_code=503,
                detail="ASR service not available. Please configure DASHSCOPE_API_KEY."
            )

        # 瑙ｇ爜 Base64 闊抽鏁版嵁
        try:
            audio_bytes = base64.b64decode(request.audio_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64 audio data: {str(e)}")

        # 璋冪敤 ASR 鏈嶅姟
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
    """ASR upload endpoint receiving audio file."""
    try:
        asr_service = get_asr_service()

        if not asr_service.enabled:
            raise HTTPException(
                status_code=503,
                detail="ASR service not available. Please configure DASHSCOPE_API_KEY."
            )

        # 璇诲彇鏂囦欢鍐呭
        audio_bytes = await file.read()

        # 鏍规嵁鏂囦欢鎵╁睍鍚嶇‘瀹氭牸寮?        filename = file.filename or "audio.wav"
        format_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"

        # 璋冪敤 ASR 鏈嶅姟
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
    """Get ASR service status."""
    asr_service = get_asr_service()
    return {
        "enabled": asr_service.enabled,
        "api_key_configured": bool(settings.dashscope_api_key)
    }


# ==================== TTS 鏂囧瓧杞闊?API ====================

class TTSRequest(BaseModel):
    """TTS request payload."""
    text: str
    voice: str = "longxiaochun"  # 榛樿濂冲０


@app.post("/api/tts/synthesize")
async def synthesize_speech(request: TTSRequest):
    """Text-to-speech synthesis endpoint."""
    try:
        tts_service = get_tts_service()

        if not tts_service.enabled:
            raise HTTPException(
                status_code=503,
                detail="TTS service not available. Please configure DASHSCOPE_API_KEY."
            )

        result = tts_service.synthesize(
            text=request.text,
            voice=request.voice
        )

        if result["success"]:
            return {
                "success": True,
                "audio": result["audio"],
                "format": result["format"],
                "voice": result["voice"]
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Unknown error")
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS processing error: {str(e)}")


@app.get("/api/tts/voices")
async def get_tts_voices():
    """Get available TTS voices."""
    return {
        "voices": AVAILABLE_VOICES,
        "default": "longxiaochun"
    }


@app.get("/api/tts/status")
async def get_tts_status():
    """Get TTS service status."""
    tts_service = get_tts_service()
    return {
        "enabled": tts_service.enabled,
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
