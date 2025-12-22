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
from contextlib import asynccontextmanager

from common.config import settings
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
from agent import (
    AgentState,
    ToolEvent,
    create_checkpointer,
    create_research_graph,
    event_stream_generator,
    get_deep_agent_prompt,
    get_default_agent_prompt,
    get_emitter,
    initialize_enhanced_tools,
    remove_emitter,
)
from support_agent import create_support_graph
from tools.mcp import init_mcp_tools, close_mcp_tools, reload_mcp_tools
from tools.core.registry import set_registered_tools
from tools.core.memory_client import fetch_memories, add_memory_entry, store_interaction
from tools.io.asr import get_asr_service, init_asr_service
from tools.io.tts import get_tts_service, init_tts_service, AVAILABLE_VOICES
from common.logger import setup_logging, get_logger, LogContext
from common.metrics import metrics_registry
from common.cancellation import cancellation_manager
from tools.browser.browser_session import browser_sessions
from tools.sandbox import sandbox_browser_sessions
from tools.io.screenshot_service import get_screenshot_service, init_screenshot_service
from common.agents_store import (
    AgentProfile,
    ensure_default_agent,
    load_agents,
    get_agent as get_agent_profile,
    upsert_agent as upsert_agent_profile,
    delete_agent as delete_agent_profile,
)
from triggers import (
    TriggerManager,
    get_trigger_manager,
    init_trigger_manager,
    shutdown_trigger_manager,
    ScheduledTrigger,
    WebhookTrigger,
    EventTrigger,
    TriggerType,
    TriggerStatus,
)
from prometheus_client import (
    Counter,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
)


# Initialize logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await startup_event()
    try:
        yield
    finally:
        # Shutdown
        await shutdown_event()


# Initialize FastAPI app
app = FastAPI(
    title="Manus Research Agent API",
    description="Deep  research AI agent with code execution capabilities",
    version="0.1.0",
    lifespan=lifespan,
)

# Prometheus metrics (optional, made idempotent to survive double imports under reload)
def _get_or_create_counter(name: str, *args, **kwargs):
    existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
    if existing:
        return existing
    return Counter(name, *args, **kwargs)


def _get_or_create_gauge(name: str, *args, **kwargs):
    existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
    if existing:
        return existing
    return Gauge(name, *args, **kwargs)


http_requests_total = (
    _get_or_create_counter("weaver_http_requests_total", "Total HTTP requests", ["method", "path", "status"])
    if settings.enable_prometheus
    else None
)
http_inprogress = (
    _get_or_create_gauge("weaver_http_inprogress", "In-flight HTTP requests")
    if settings.enable_prometheus
    else None
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing information."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    if http_inprogress:
        http_inprogress.inc()

        logger.info(
            f"Request started | {request.method} {request.url.path} | "
            f"ID: {request_id} | Client: {request.client.host if request.client else 'unknown'}"
        )

    try:
        response = await call_next(request)
        duration = time.time() - start_time

        logger.info(
            f"Request completed | {request.method} {request.url.path} | "
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
    checkpointer = MemorySaver()

def _init_store():
    backend = settings.memory_store_backend.lower().strip()
    url = settings.memory_store_url.strip()
    if backend == "postgres":
        if not url:
            raise ValueError("memory_store_url is required when memory_store_backend=postgres")
        from langgraph.store.postgres import PostgresStore
        store_obj = PostgresStore.from_conn_string(url)
        store_obj.setup()
        logger.info("Initialized PostgresStore for long-term memory")
        return store_obj
    if backend == "redis":
        if not url:
            raise ValueError("memory_store_url is required when memory_store_backend=redis")
        from langgraph.store.redis import RedisStore
        store_obj = RedisStore.from_conn_string(url)
        store_obj.setup()
        logger.info("Initialized RedisStore for long-term memory")
        return store_obj

    logger.info("Using in-memory store (disabled persistent store)")
    return None

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


async def startup_event():
    """Initialize application on startup."""
    logger.info("=" * 80)
    logger.info("Weaver Research Agent Starting...")
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
        # Attach thread_id for emitter separation
        if isinstance(mcp_servers_config, dict):
            mcp_servers_config["__thread_id__"] = "default"
        mcp_tools = await init_mcp_tools(servers_override=mcp_servers_config, enabled=mcp_enabled)
        if mcp_tools:
            set_registered_tools(mcp_tools)
            mcp_loaded_tools = len(mcp_tools)
            logger.info(f"Successfully registered {mcp_loaded_tools} MCP tools")
        else:
            logger.info("No MCP tools to register")
            mcp_loaded_tools = 0
    except Exception as e:
        logger.warning(f"MCP tools initialization failed: {e}", exc_info=settings.debug)
        mcp_loaded_tools = 0

    # Initialize enhanced tool system (Phase 1-4)
    try:
        logger.info("Initializing enhanced tool system (Phase 1-4)...")
        initialize_enhanced_tools()
        logger.info("Enhanced tool system initialized")
    except Exception as e:
        logger.warning(f"Enhanced tool system initialization failed: {e}", exc_info=settings.debug)

    # Initialize ASR service
    if settings.dashscope_api_key:
        try:
            logger.info("Initializing ASR service...")
            init_asr_service(settings.dashscope_api_key)
            logger.info("ASR service initialized")
        except Exception as e:
            logger.warning(f"ASR service initialization failed: {e}")
    else:
        logger.info("ASR service not configured (no DASHSCOPE_API_KEY)")

    # Initialize TTS service
    if settings.dashscope_api_key:
        try:
            logger.info("Initializing TTS service...")
            init_tts_service(settings.dashscope_api_key)
            logger.info("TTS service initialized")
        except Exception as e:
            logger.warning(f"TTS service initialization failed: {e}")
    else:
        logger.info("TTS service not configured (no DASHSCOPE_API_KEY)")

    # Ensure local agents store exists (GPTs-like profiles)
    try:
        # Default agent: basic tools
        ensure_default_agent(
            default_profile=AgentProfile(
                id="default",
                name="Weaver Default Agent",
                description="Default tool-using agent profile for agent mode.",
                system_prompt=get_default_agent_prompt(),
                enabled_tools={
                    "web_search": True,
                    "browser": True,
                    "crawl": True,
                    "python": True,
                    "mcp": True,
                },
                metadata={"protected": True},
            )
        )

        # Manus-like agent: all sandbox tools enabled
        ensure_default_agent(
            default_profile=AgentProfile(
                id="manus",
                name="Manus Agent",
                description="Full-featured agent with all sandbox tools (like Manus). Supports file operations, shell commands, Excel, PPT, image editing, and more.",
                system_prompt=get_default_agent_prompt(),
                enabled_tools={
                    # Core tools
                    "web_search": True,
                    "crawl": True,
                    "python": True,
                    "mcp": True,
                    "task_list": True,
                    # Sandbox browser
                    "sandbox_browser": True,
                    "sandbox_web_search": True,
                    # Sandbox file operations
                    "sandbox_files": True,
                    "sandbox_shell": True,
                    # Web dev & deploy
                    "sandbox_web_dev": True,
                    # Document generation
                    "sandbox_sheets": True,
                    "sandbox_presentation": True,
                    "presentation_outline": True,
                    "presentation_v2": True,
                    # Image processing
                    "sandbox_vision": True,
                    "sandbox_image_edit": True,
                    # Desktop automation
                    "computer_use": True,
                },
                metadata={"protected": True},
            )
        )
        logger.info("Agents store initialized (data/agents.json)")
    except Exception as e:
        logger.warning(f"Agents store init failed: {e}", exc_info=settings.debug)

    logger.info("=" * 80)
    logger.info("Weaver Research Agent Ready")
    logger.info("=" * 80)

    # Initialize trigger system
    try:
        logger.info("Initializing trigger system...")
        await init_trigger_manager(storage_path="data/triggers.json")
        logger.info("Trigger system initialized successfully")
    except Exception as e:
        logger.warning(f"Trigger system initialization failed: {e}", exc_info=settings.debug)


async def shutdown_event():
    """Cleanup on application shutdown."""
    logger.info("=" * 80)
    logger.info("Weaver Research Agent Shutting Down...")
    logger.info("=" * 80)

    try:
        logger.info("Closing MCP tools...")
        await close_mcp_tools()
        logger.info("MCP tools closed successfully")
    except Exception as e:
        logger.error(f"Error closing MCP tools: {e}", exc_info=True)

    # Best-effort stop all Daytona sandboxes
    try:
        from tools.sandbox.daytona_client import daytona_stop_all
        daytona_stop_all(thread_id="default")
    except Exception as e:
        logger.warning(f"Error stopping Daytona sandboxes: {e}")

    # Shutdown trigger system
    try:
        logger.info("Shutting down trigger system...")
        await shutdown_trigger_manager()
        logger.info("Trigger system shutdown successfully")
    except Exception as e:
        logger.error(f"Error shutting down trigger system: {e}", exc_info=True)

    logger.info("=" * 80)
    logger.info("Shutdown Complete")
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
    model: Optional[str] = None
    search_mode: Optional[SearchMode | Dict[str, Any] | str] = None  # {"useWebSearch": bool, "useAgent": bool, "useDeepSearch": bool}
    agent_id: Optional[str] = None  # optional GPTs-like agent profile id (data/agents.json)
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
    model: Optional[str] = None
    search_mode: Optional[SearchMode | Dict[str, Any] | str] = None
    agent_id: Optional[str] = None


class MCPConfigPayload(BaseModel):
    enable: Optional[bool] = None
    servers: Optional[Dict[str, Any]] = None


class AgentUpsertPayload(BaseModel):
    id: Optional[str] = None
    name: str
    description: str = ""
    system_prompt: str = ""
    model: str = ""
    enabled_tools: Dict[str, bool] = {}
    mcp_servers: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}


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


# Store active streaming tasks (legacy; cancellation is primarily token-based)
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
        "stats": cancellation_manager.get_stats(),
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
        use_deep_prompt = use_deep
    elif isinstance(search_mode, dict):
        # Support both camelCase (frontend payload) and snake_case (already-normalized)
        use_web = bool(search_mode.get("useWebSearch", search_mode.get("use_web", False)))
        use_agent = bool(search_mode.get("useAgent", search_mode.get("use_agent", False)))
        use_deep = bool(search_mode.get("useDeepSearch", search_mode.get("use_deep", False)))
        use_deep_prompt = bool(search_mode.get("useDeepPrompt", search_mode.get("use_deep_prompt", use_deep)))

        # If booleans were not provided but a mode string exists, derive flags from it
        if not (use_web or use_agent or use_deep) and isinstance(search_mode.get("mode"), str):
            mode_lower = search_mode["mode"].strip().lower()
            if mode_lower == "web":
                use_web = True
            elif mode_lower in {"agent", "deep"}:
                use_agent = True
                use_deep = mode_lower == "deep"
                use_deep_prompt = use_deep
    elif isinstance(search_mode, str):
        lowered = search_mode.lower().strip()

        # UX labels
        if lowered in {"direct", ""}:
            use_web = False
            use_agent = False
            use_deep = False
            use_deep_prompt = False
        else:
            use_web = lowered in {"web", "search", "tavily"}
            use_agent = lowered in {"agent", "deep", "deep_agent", "deep-agent", "ultra"}
            use_deep = lowered in {"deep", "deep_agent", "deep-agent", "ultra"}
            use_deep_prompt = use_deep
    else:
        use_web = False
        use_agent = False
        use_deep = False
        use_deep_prompt = False

    if use_deep and not use_agent:
        use_deep = False
        use_deep_prompt = False

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
        "use_deep_prompt": use_deep_prompt,
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
    model: str | None = None,
    search_mode: Dict[str, Any] | None = None,
    agent_id: str | None = None,
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
    was_interrupted = False
    images = images or []
    user_id = user_id or settings.memory_user_id
    model = (model or settings.primary_model).strip()
    agent_id = (agent_id or "default").strip() or "default"
    agent_profile = get_agent_profile(agent_id) or get_agent_profile("default")

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

    # Set up event emitter for tool visualization
    emitter = await get_emitter(thread_id)
    event_queue: asyncio.Queue = asyncio.Queue()

    async def tool_event_listener(event):
        """Forward tool events to the queue for SSE streaming."""
        await event_queue.put(event)

    emitter.on_event(tool_event_listener)

    try:
        logger.info(f"Agent stream started | Thread: {thread_id} | Model: {model}")
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
        if mode_info.get("mode") == "agent" and agent_profile and agent_profile.system_prompt:
            messages.append(SystemMessage(content=agent_profile.system_prompt))
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
                "agent_profile": agent_profile.model_dump(mode="json") if agent_profile else None,
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
            # First, drain any pending tool events from the queue
            while not event_queue.empty():
                try:
                    tool_event = event_queue.get_nowait()
                    # Forward tool events to SSE stream
                    if tool_event.type == ToolEvent.TOOL_START:
                        yield await format_stream_event("tool_start", tool_event.data)
                    elif tool_event.type == ToolEvent.TOOL_SCREENSHOT:
                        yield await format_stream_event("screenshot", tool_event.data)
                    elif tool_event.type == ToolEvent.TOOL_RESULT:
                        yield await format_stream_event("tool_result", tool_event.data)
                    elif tool_event.type == ToolEvent.TOOL_ERROR:
                        yield await format_stream_event("tool_error", tool_event.data)
                    elif tool_event.type == ToolEvent.TASK_UPDATE:
                        yield await format_stream_event("task_update", tool_event.data)
                except asyncio.QueueEmpty:
                    break

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
                    logger.debug(f"  Clarify node started | Thread: {thread_id}")
                    yield await format_stream_event("status", {
                        "text": "Checking if clarification is needed...",
                        "step": "clarifying"
                    })
                elif "planner" in node_name:
                    logger.debug(f"  Planning node started | Thread: {thread_id}")
                    yield await format_stream_event("status", {
                        "text": "Creating research plan...",
                        "step": "planning"
                    })
                elif "perform_parallel_search" in node_name or "search" in node_name:
                    logger.debug(f"  Search node started | Thread: {thread_id}")
                    yield await format_stream_event("status", {
                        "text": "Conducting research...",
                        "step": "researching"
                    })
                elif "writer" in node_name:
                    logger.debug(f"  Writer node started | Thread: {thread_id}")
                    yield await format_stream_event("status", {
                        "text": "Synthesizing findings...",
                        "step": "writing"
                    })
                elif node_name == "agent":
                    logger.debug(f"  Agent node started | Thread: {thread_id}")
                    yield await format_stream_event("status", {
                        "text": "Running agent (tool-calling)...",
                        "step": "agent"
                    })

            elif event_type in {"on_chain_end", "on_node_end", "on_graph_end"}:
                output = data_dict.get("output", {}) if isinstance(data_dict, dict) else {}
                metrics.mark_event(event_type, node_name)

                # Extract messages from output
                if isinstance(output, dict):
                    # Interrupt handling
                    interrupts = output.get("__interrupt__")
                    if interrupts:
                        was_interrupted = True
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
                # Browser screenshots (optional Playwright)
                if tool_name == "browser_screenshot" and isinstance(output, dict):
                    image_data = output.get("image")
                    url = output.get("url", "")
                    if image_data:
                        yield await format_stream_event("artifact", {
                            "id": f"art_{datetime.now().timestamp()}",
                            "type": "chart",
                            "title": "Browser Screenshot",
                            "content": url or "Screenshot",
                            "image": image_data
                        })
                # Sandbox browser tools (E2B + Playwright CDP)
                if tool_name.startswith("sb_browser_") and isinstance(output, dict):
                    image_data = output.get("image")
                    url = output.get("url", "")
                    if isinstance(image_data, str) and image_data.strip():
                        yield await format_stream_event("artifact", {
                            "id": f"art_{datetime.now().timestamp()}",
                            "type": "chart",
                            "title": f"Sandbox Browser ({tool_name})",
                            "content": url or tool_name,
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
        # Cleanup event emitter listener
        try:
            emitter.off_event(tool_event_listener)
            await remove_emitter(thread_id)
        except Exception:
            pass
        # ???????
        if thread_id in active_streams:
            del active_streams[thread_id]
        if thread_handler:
            try:
                root_logger.removeHandler(thread_handler)
                thread_handler.close()
            except Exception:
                pass
        # Clean up browser sessions when the run is truly finished.
        # If the graph interrupted (HITL), keep sessions so /api/interrupt/resume can continue.
        if not was_interrupted:
            try:
                browser_sessions.reset(thread_id)
            except Exception:
                pass
            try:
                sandbox_browser_sessions.reset(thread_id)
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
        model = (request.model or settings.primary_model).strip()
        agent_id = (request.agent_id or "default").strip() or "default"
        agent_profile = get_agent_profile(agent_id) or get_agent_profile("default")

        logger.info("Chat request received")
        logger.info(f"  Model: {model}")
        logger.info(f"  Raw search_mode: {request.search_mode}")
        logger.info(f"  Normalized mode_info: {mode_info}")
        logger.info(f"  Final mode: {mode_info.get('mode')}")
        logger.info(f"  Stream: {request.stream}")
        logger.info(f"  Message length: {len(last_message)} chars")
        logger.debug(f"  Message preview: {last_message[:200]}...")

        if request.stream:
            thread_id = f"thread_{uuid.uuid4().hex}"
            logger.info(f"Starting streaming response | Thread: {thread_id}")

            # Return streaming response with thread_id in header for cancellation
            return StreamingResponse(
                stream_agent_events(
                    last_message,
                    thread_id=thread_id,
                    model=model,
                    search_mode=mode_info,
                    agent_id=request.agent_id,
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
            if mode_info.get("mode") == "agent" and agent_profile and agent_profile.system_prompt:
                messages.append(SystemMessage(content=agent_profile.system_prompt))
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
                    "model": model,
                    "search_mode": mode_info,
                    "agent_profile": agent_profile.model_dump(mode="json") if agent_profile else None,
                    "user_id": user_id,
                    "allow_interrupts": bool(checkpointer),
                    "tool_approval": settings.tool_approval or False,
                    "human_review": settings.human_review or False,
                    "max_revisions": settings.max_revisions,
                },
                "recursion_limit": 50,
            }
            thread_id = thread_id or f"thread_{uuid.uuid4().hex}"
            metrics = metrics_registry.start(thread_id, model=model, route=mode_info.get("mode", "direct"))
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
            f"Model: {model if 'model' in locals() else (request.model if 'request' in locals() else 'N/A')} | "
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
    model = (request.model or settings.primary_model).strip()
    agent_id = (request.agent_id or "default").strip() or "default"
    agent_profile = get_agent_profile(agent_id) or get_agent_profile("default")
    # Fast path: avoid invoking the graph when no checkpoint exists for this thread.
    if not request.thread_id or not str(request.thread_id).strip():
        raise HTTPException(status_code=400, detail="thread_id is required")
    existing = checkpointer.get_tuple({"configurable": {"thread_id": request.thread_id}})
    if not existing:
        raise HTTPException(status_code=404, detail="No checkpoint found for this thread_id")
    config = {
        "configurable": {
            "thread_id": request.thread_id,
            "model": model,
            "search_mode": mode_info,
            "agent_profile": agent_profile.model_dump(mode="json") if agent_profile else None,
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


# ==================== Agents (GPTs-like profiles) ====================

@app.get("/api/agents")
async def list_agents():
    profiles = load_agents()
    return {"agents": [p.model_dump(mode="json") for p in profiles]}


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    profile = get_agent_profile(agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent not found")
    return profile.model_dump(mode="json")


@app.post("/api/agents")
async def create_agent(payload: AgentUpsertPayload):
    agent_id = (payload.id or "").strip() or f"agent_{uuid.uuid4().hex[:10]}"
    profile = AgentProfile(
        id=agent_id,
        name=payload.name.strip(),
        description=payload.description or "",
        system_prompt=payload.system_prompt or "",
        model=(payload.model or "").strip(),
        enabled_tools=payload.enabled_tools or {},
        mcp_servers=payload.mcp_servers,
        metadata=payload.metadata or {},
    )
    saved = upsert_agent_profile(profile)
    return saved.model_dump(mode="json")


@app.put("/api/agents/{agent_id}")
async def update_agent(agent_id: str, payload: AgentUpsertPayload):
    existing = get_agent_profile(agent_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent_id == "default":
        raise HTTPException(status_code=400, detail="Default agent is protected")

    profile = existing.model_copy(
        update={
            "name": payload.name.strip(),
            "description": payload.description or "",
            "system_prompt": payload.system_prompt or "",
            "model": (payload.model or "").strip(),
            "enabled_tools": payload.enabled_tools or {},
            "mcp_servers": payload.mcp_servers,
            "metadata": payload.metadata or {},
        }
    )
    saved = upsert_agent_profile(profile)
    return saved.model_dump(mode="json")


@app.delete("/api/agents/{agent_id}")
async def remove_agent(agent_id: str):
    if agent_id == "default":
        raise HTTPException(status_code=400, detail="Default agent is protected")
    ok = delete_agent_profile(agent_id, protected_ids={"default"})
    if not ok:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "deleted", "id": agent_id}


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



@app.get("/api/memory/status")
async def memory_status():
    """Return memory backend status and configuration."""
    backend = settings.memory_store_backend
    url = settings.memory_store_url
    return {
        "backend": backend,
        "url_configured": bool(url),
        "checkpointer": bool(checkpointer),
        "mem0_enabled": settings.enable_memory,
    }

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

        # Determine format from file extension
        filename = file.filename or "audio.wav"
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


# ==================== Screenshot API ====================

from fastapi.responses import FileResponse

@app.get("/api/screenshots/{filename}")
async def get_screenshot(filename: str):
    """
    Serve a screenshot file.

    Args:
        filename: Screenshot filename
    """
    service = get_screenshot_service()
    filepath = service.get_screenshot_path(filename)

    if not filepath:
        raise HTTPException(status_code=404, detail="Screenshot not found")

    # Determine media type
    media_type = "image/png"
    if filename.lower().endswith(".jpg") or filename.lower().endswith(".jpeg"):
        media_type = "image/jpeg"

    return FileResponse(
        filepath,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"}
    )


@app.get("/api/screenshots")
async def list_screenshots(thread_id: Optional[str] = None, limit: int = 50):
    """
    List available screenshots.

    Args:
        thread_id: Optional filter by thread ID
        limit: Maximum number of results
    """
    service = get_screenshot_service()
    screenshots = service.list_screenshots(thread_id=thread_id, limit=limit)

    return {
        "screenshots": screenshots,
        "count": len(screenshots),
        "thread_id": thread_id
    }


@app.post("/api/screenshots/cleanup")
async def cleanup_screenshots():
    """Cleanup old screenshots."""
    service = get_screenshot_service()
    deleted_count = await service.cleanup_old_screenshots()

    return {
        "status": "completed",
        "deleted_count": deleted_count,
        "timestamp": datetime.now().isoformat()
    }


# ==================== Tool Events SSE Endpoint ====================

@app.get("/api/events/{thread_id}")
async def stream_tool_events(thread_id: str):
    """
    Subscribe to tool execution events for a specific thread.

    This endpoint streams real-time events including:
    - tool_start: When a tool begins execution
    - tool_screenshot: When a screenshot is captured
    - tool_result: When a tool completes execution
    - task_update: Task progress updates

    Usage:
        const eventSource = new EventSource('/api/events/thread_123');
        eventSource.onmessage = (e) => {
            const data = JSON.parse(e.data);
            console.log(data.type, data.data);
        };
    """
    async def event_generator():
        async for event_sse in event_stream_generator(thread_id, timeout=300.0):
            yield event_sse

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ==================== Trigger System Endpoints ====================

class CreateScheduledTriggerRequest(BaseModel):
    name: str
    description: str = ""
    schedule: str  # Cron expression
    agent_id: str = "default"
    task: str
    task_params: Dict[str, Any] = {}
    timezone: str = "Asia/Shanghai"
    run_immediately: bool = False
    user_id: Optional[str] = None
    tags: List[str] = []


class CreateWebhookTriggerRequest(BaseModel):
    name: str
    description: str = ""
    agent_id: str = "default"
    task: str
    task_params: Dict[str, Any] = {}
    http_methods: List[str] = ["POST"]
    require_auth: bool = False
    rate_limit: Optional[int] = None
    user_id: Optional[str] = None
    tags: List[str] = []


class CreateEventTriggerRequest(BaseModel):
    name: str
    description: str = ""
    event_type: str
    event_source: Optional[str] = None
    event_filters: Dict[str, Any] = {}
    agent_id: str = "default"
    task: str
    task_params: Dict[str, Any] = {}
    debounce_seconds: int = 0
    user_id: Optional[str] = None
    tags: List[str] = []


@app.post("/api/triggers/scheduled")
async def create_scheduled_trigger(request: CreateScheduledTriggerRequest):
    """Create a new scheduled trigger with cron expression."""
    trigger = ScheduledTrigger(
        name=request.name,
        description=request.description,
        schedule=request.schedule,
        agent_id=request.agent_id,
        task=request.task,
        task_params=request.task_params,
        timezone=request.timezone,
        run_immediately=request.run_immediately,
        user_id=request.user_id,
        tags=request.tags,
    )

    manager = get_trigger_manager()
    trigger_id = await manager.add_trigger(trigger)

    return {
        "success": True,
        "trigger_id": trigger_id,
        "trigger": trigger.to_dict(),
    }


@app.post("/api/triggers/webhook")
async def create_webhook_trigger(request: CreateWebhookTriggerRequest):
    """Create a new webhook trigger."""
    trigger = WebhookTrigger(
        name=request.name,
        description=request.description,
        agent_id=request.agent_id,
        task=request.task,
        task_params=request.task_params,
        http_methods=request.http_methods,
        require_auth=request.require_auth,
        rate_limit=request.rate_limit,
        user_id=request.user_id,
        tags=request.tags,
    )

    # Generate auth token if authentication is required
    if trigger.require_auth:
        from triggers.webhook import get_webhook_handler
        trigger.auth_token = get_webhook_handler().generate_auth_token()

    manager = get_trigger_manager()
    trigger_id = await manager.add_trigger(trigger)

    response = {
        "success": True,
        "trigger_id": trigger_id,
        "trigger": trigger.to_dict(),
        "endpoint": trigger.endpoint_path,
    }

    if trigger.require_auth:
        response["auth_token"] = trigger.auth_token

    return response


@app.post("/api/triggers/event")
async def create_event_trigger(request: CreateEventTriggerRequest):
    """Create a new event trigger."""
    trigger = EventTrigger(
        name=request.name,
        description=request.description,
        event_type=request.event_type,
        event_source=request.event_source,
        event_filters=request.event_filters,
        agent_id=request.agent_id,
        task=request.task,
        task_params=request.task_params,
        debounce_seconds=request.debounce_seconds,
        user_id=request.user_id,
        tags=request.tags,
    )

    manager = get_trigger_manager()
    trigger_id = await manager.add_trigger(trigger)

    return {
        "success": True,
        "trigger_id": trigger_id,
        "trigger": trigger.to_dict(),
    }


@app.get("/api/triggers")
async def list_triggers(
    trigger_type: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
):
    """List all triggers with optional filtering."""
    manager = get_trigger_manager()

    type_filter = TriggerType(trigger_type) if trigger_type else None
    status_filter = TriggerStatus(status) if status else None

    triggers = manager.list_triggers(
        trigger_type=type_filter,
        status=status_filter,
        user_id=user_id,
    )

    return {
        "triggers": [t.to_dict() for t in triggers],
        "total": len(triggers),
    }


@app.get("/api/triggers/{trigger_id}")
async def get_trigger(trigger_id: str):
    """Get a specific trigger by ID."""
    manager = get_trigger_manager()
    trigger = manager.get_trigger(trigger_id)

    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    return {"trigger": trigger.to_dict()}


@app.delete("/api/triggers/{trigger_id}")
async def delete_trigger(trigger_id: str):
    """Delete a trigger."""
    manager = get_trigger_manager()
    success = await manager.remove_trigger(trigger_id)

    if not success:
        raise HTTPException(status_code=404, detail="Trigger not found")

    return {"success": True, "message": "Trigger deleted"}


@app.post("/api/triggers/{trigger_id}/pause")
async def pause_trigger(trigger_id: str):
    """Pause a trigger."""
    manager = get_trigger_manager()
    success = await manager.pause_trigger(trigger_id)

    if not success:
        raise HTTPException(status_code=404, detail="Trigger not found")

    return {"success": True, "message": "Trigger paused"}


@app.post("/api/triggers/{trigger_id}/resume")
async def resume_trigger(trigger_id: str):
    """Resume a paused trigger."""
    manager = get_trigger_manager()
    success = await manager.resume_trigger(trigger_id)

    if not success:
        raise HTTPException(status_code=404, detail="Trigger not found or not paused")

    return {"success": True, "message": "Trigger resumed"}


@app.get("/api/triggers/{trigger_id}/executions")
async def get_trigger_executions(trigger_id: str, limit: int = 50):
    """Get execution history for a trigger."""
    manager = get_trigger_manager()
    executions = manager.get_executions(trigger_id=trigger_id, limit=limit)

    return {
        "executions": [e.to_dict() for e in executions],
        "total": len(executions),
    }


@app.post("/api/webhook/{trigger_id}")
async def handle_webhook(
    trigger_id: str,
    request: Request,
):
    """Handle incoming webhook requests."""
    manager = get_trigger_manager()

    # Extract request data
    body = None
    try:
        body = await request.json()
    except Exception:
        pass

    query_params = dict(request.query_params)
    headers = dict(request.headers)
    auth_header = request.headers.get("Authorization")

    result = await manager.handle_webhook(
        trigger_id=trigger_id,
        method=request.method,
        body=body,
        query_params=query_params,
        headers=headers,
        auth_header=auth_header,
    )

    status_code = result.pop("status_code", 200)

    if not result.get("success"):
        raise HTTPException(status_code=status_code, detail=result.get("error"))

    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info"
    )
