import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    generate_latest,
)
from pydantic import BaseModel, field_validator

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
from agent.workflows.evidence_extractor import extract_message_sources
from common.agents_store import (
    AgentProfile,
    ensure_default_agent,
    load_agents,
)
from common.agents_store import (
    delete_agent as delete_agent_profile,
)
from common.agents_store import (
    get_agent as get_agent_profile,
)
from common.agents_store import (
    upsert_agent as upsert_agent_profile,
)
from common.cancellation import TaskStatus, cancellation_manager
from common.chat_stream_translate import translate_legacy_line_to_sse
from common.config import settings
from common.logger import get_logger, setup_logging
from common.metrics import metrics_registry
from common.sse import format_sse_event, iter_with_sse_keepalive
from common.thread_ownership import get_thread_owner, set_thread_owner
from support_agent import create_support_graph
from tools.browser.browser_session import browser_sessions
from tools.core.memory_client import add_memory_entry, fetch_memories, store_interaction
from tools.core.registry import set_registered_tools
from tools.io.asr import get_asr_service, init_asr_service
from tools.io.screenshot_service import get_screenshot_service
from tools.io.tts import AVAILABLE_VOICES, get_tts_service, init_tts_service
from tools.mcp import close_mcp_tools, init_mcp_tools, reload_mcp_tools
from tools.sandbox import sandbox_browser_sessions
from tools.search.multi_search import get_search_orchestrator
from triggers import (
    EventTrigger,
    ScheduledTrigger,
    TriggerStatus,
    TriggerType,
    WebhookTrigger,
    get_trigger_manager,
    init_trigger_manager,
    shutdown_trigger_manager,
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
    title="Weaver Research Agent API",
    description="Deep  research AI agent with code execution capabilities",
    version="0.1.0",
    lifespan=lifespan,
)

APP_STARTED_AT = time.monotonic()


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
    _get_or_create_counter(
        "weaver_http_requests_total", "Total HTTP requests", ["method", "path", "status"]
    )
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
    """Log all HTTP requests, enforce internal auth, and apply basic rate limiting."""
    request_id = (request.headers.get("X-Request-ID") or "").strip() or str(uuid.uuid4())[:8]
    start_time = time.time()

    if http_inprogress:
        http_inprogress.inc()

    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    auth_user_header = (getattr(settings, "auth_user_header", "") or "").strip() or "X-Weaver-User"
    path = request.url.path
    method = request.method.upper()

    principal_id = ((request.headers.get(auth_user_header) or "").strip() if internal_key else "").strip()
    request.state.principal_id = principal_id or ("internal" if internal_key else "anonymous")

    logger.info(
        f"Request started | {request.method} {request.url.path} | "
        f"ID: {request_id} | Client: {request.client.host if request.client else 'unknown'}"
    )

    try:
        should_auth = (
            internal_key
            and path.startswith("/api/")
            and not path.startswith("/api/webhook/")
            and method != "OPTIONS"
        )
        provided = ""
        if should_auth:
            auth_header = (request.headers.get("Authorization") or "").strip()
            if auth_header.lower().startswith("bearer "):
                provided = auth_header[7:].strip()
            if not provided:
                provided = (request.headers.get("X-API-Key") or "").strip()

        authorized = (not should_auth) or (provided and hmac.compare_digest(provided, internal_key))

        # Basic in-memory rate limiting (token bucket) with response headers.
        rate_limit_limit = 0
        rate_limit_remaining = 0
        rate_limit_reset_ts = 0
        rate_limit_exceeded = False
        rate_limit_retry_after = 0
        if path not in _RATE_LIMIT_EXEMPT and method != "OPTIONS":
            identity = (
                (getattr(request.state, "principal_id", "") or "").strip()
                if internal_key and authorized
                else _get_client_ip(request)
            )
            is_chat = path.startswith("/api/chat")
            rate_limit_limit = _RATE_LIMIT_CHAT if is_chat else _RATE_LIMIT_GENERAL
            bucket_key = f"{identity}:{'chat' if is_chat else 'general'}"
            now = time.time()

            bucket = _rate_limit_buckets.get(bucket_key)
            if bucket is None or now - bucket["window_start"] >= _RATE_LIMIT_WINDOW:
                bucket = {"tokens": rate_limit_limit - 1, "window_start": now}
                _rate_limit_buckets[bucket_key] = bucket
            else:
                bucket["tokens"] -= 1

            rate_limit_remaining = int(max(bucket.get("tokens", 0), 0))
            rate_limit_reset_ts = int(bucket["window_start"] + _RATE_LIMIT_WINDOW)

            if bucket.get("tokens", 0) < 0:
                rate_limit_exceeded = True
                rate_limit_retry_after = int(_RATE_LIMIT_WINDOW - (now - bucket["window_start"])) + 1

        if rate_limit_exceeded:
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please slow down.",
                    "retry_after": rate_limit_retry_after,
                },
                headers={"Retry-After": str(rate_limit_retry_after)},
            )
        elif not authorized:
            response = JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "status_code": 401,
                    "request_id": request_id,
                    "timestamp": datetime.now().isoformat(),
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        if rate_limit_limit:
            _apply_rate_limit_headers(
                response,
                limit=rate_limit_limit,
                remaining=0 if rate_limit_exceeded else rate_limit_remaining,
                reset_ts=rate_limit_reset_ts,
            )
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
            exc_info=True,
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
    expose_headers=["X-Thread-ID", "X-Request-ID"],  # Allow frontend to read these headers
)


# ---------------------------------------------------------------------------
# Rate Limiting Middleware (in-memory token bucket)
# ---------------------------------------------------------------------------
_rate_limit_buckets: Dict[str, Dict[str, Any]] = {}
_RATE_LIMIT_GENERAL = 60  # requests per minute for general endpoints
_RATE_LIMIT_CHAT = 20  # requests per minute for chat endpoints
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_EXEMPT = {"/", "/health", "/metrics", "/docs", "/openapi.json", "/redoc"}
_rate_limit_cleanup_task: asyncio.Task | None = None


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind a reverse proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _apply_rate_limit_headers(response: Any, *, limit: int, remaining: int, reset_ts: int) -> None:
    if not hasattr(response, "headers"):
        return
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(remaining, 0))
    response.headers["X-RateLimit-Reset"] = str(reset_ts)


def _require_thread_owner(request: Request, thread_id: str) -> None:
    """
    Enforce per-user thread isolation when internal auth is enabled.

    Uses best-effort ownership sources:
    - In-memory thread ownership registry (SSE-created threads)
    - Persisted session state via checkpointer (if present)
    """
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    if not internal_key:
        return

    principal_id = (getattr(request.state, "principal_id", "") or "").strip()
    if not principal_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    owner_id = (get_thread_owner(thread_id) or "").strip()
    if owner_id and owner_id != principal_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not checkpointer:
        return

    try:
        from common.session_manager import get_session_manager

        manager = get_session_manager(checkpointer)
        session_state = manager.get_session_state(thread_id)
        if not session_state or not isinstance(session_state.state, dict):
            return
        persisted_owner = session_state.state.get("user_id")
        if isinstance(persisted_owner, str) and persisted_owner.strip() and persisted_owner.strip() != principal_id:
            raise HTTPException(status_code=403, detail="Forbidden")
    except HTTPException:
        raise
    except Exception:
        # Authorization is best-effort; never 500 due to ownership lookups.
        return


# Periodic cleanup of stale rate-limit buckets (runs every 5 minutes)
async def _cleanup_rate_limit_buckets():
    try:
        while True:
            await asyncio.sleep(300)
            now = time.time()
            stale_keys = [
                k for k, v in _rate_limit_buckets.items()
                if now - v["window_start"] > _RATE_LIMIT_WINDOW * 2
            ]
            for k in stale_keys:
                _rate_limit_buckets.pop(k, None)
    except asyncio.CancelledError:
        return


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
mcp_thread_id = "default"  # thread id for MCP event emission; per-request tools will override
mcp_enabled = settings.enable_mcp
mcp_servers_config = settings.mcp_servers
mcp_loaded_tools = 0


def _apply_mcp_thread_id(config: Any, thread_id: str) -> Any:
    """
    Ensure MCP server config carries a __thread_id__ hint for event emitters.

    Accepts dict or JSON string and returns the same type with injected field.
    """
    if not thread_id:
        return config

    if isinstance(config, str):
        try:
            parsed = json.loads(config)
        except json.JSONDecodeError:
            return config
        parsed["__thread_id__"] = thread_id
        return parsed

    if isinstance(config, dict):
        updated = dict(config)
        updated["__thread_id__"] = thread_id
        return updated

    return config


async def startup_event():
    """Initialize application on startup."""
    logger.info("=" * 80)
    logger.info("Weaver Research Agent Starting...")
    logger.info("=" * 80)

    # Ensure the rate-limit bucket cleanup task is running (lifespan-managed).
    global _rate_limit_cleanup_task
    if _rate_limit_cleanup_task is None or _rate_limit_cleanup_task.done():
        _rate_limit_cleanup_task = asyncio.create_task(
            _cleanup_rate_limit_buckets(),
            name="weaver-rate-limit-cleanup",
        )

    # Log configuration
    logger.info(f"Environment: {'DEBUG' if settings.debug else 'PRODUCTION'}")
    logger.info(f"Primary Model: {settings.primary_model}")
    logger.info(f"Reasoning Model: {settings.reasoning_model}")
    logger.info(f"Database: {'Configured' if settings.database_url else 'Not configured'}")
    logger.info(f"Checkpointer: {'Enabled' if checkpointer else 'Disabled'}")

    # Initialize MCP tools
    global mcp_loaded_tools, mcp_servers_config
    try:
        logger.info("Initializing MCP tools...")
        servers_cfg = _apply_mcp_thread_id(mcp_servers_config, mcp_thread_id)
        mcp_servers_config = servers_cfg
        mcp_tools = await init_mcp_tools(servers_override=servers_cfg, enabled=mcp_enabled)
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

        # Full-featured agent: all sandbox tools enabled (compat id: "manus")
        ensure_default_agent(
            default_profile=AgentProfile(
                id="manus",
                name="Weaver Full Agent",
                description=(
                    "Full-featured agent with all sandbox tools enabled. Supports file operations, "
                    "shell commands, spreadsheets, presentations, image editing, and more."
                ),
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

    # Stop lifespan-managed background tasks.
    global _rate_limit_cleanup_task
    cleanup_task = _rate_limit_cleanup_task
    if cleanup_task and not cleanup_task.done():
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    _rate_limit_cleanup_task = None

    try:
        logger.info("Closing MCP tools...")
        await close_mcp_tools()
        logger.info("MCP tools closed successfully")
    except Exception as e:
        logger.error(f"Error closing MCP tools: {e}", exc_info=True)

    # Best-effort stop all Daytona sandboxes
    try:
        from tools.sandbox.daytona_client import daytona_stop_all

        daytona_stop_all(thread_id=mcp_thread_id)
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


def _coerce_search_mode_input(value: Any) -> SearchMode | None:
    """
    Coerce legacy search_mode inputs into the structured SearchMode contract.

    We keep the runtime tolerant (strings / dicts) while exposing a strict OpenAPI
    schema (SearchMode object) for frontend/backend alignment.
    """
    if value is None:
        return None

    if isinstance(value, SearchMode):
        return value

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"", "direct"}:
            return SearchMode()
        if lowered in {"web", "search", "tavily"}:
            return SearchMode(useWebSearch=True)
        if lowered in {"agent"}:
            return SearchMode(useAgent=True)
        if lowered in {"deep", "deep_agent", "deep-agent", "ultra"}:
            return SearchMode(useAgent=True, useDeepSearch=True)
        # Unknown string → treat as direct.
        return SearchMode()

    if isinstance(value, dict):
        use_web = bool(value.get("useWebSearch", value.get("use_web", False)))
        use_agent = bool(value.get("useAgent", value.get("use_agent", False)))
        use_deep = bool(value.get("useDeepSearch", value.get("use_deep", False)))

        # If booleans were not provided but a mode string exists, derive flags from it.
        if not (use_web or use_agent or use_deep) and isinstance(value.get("mode"), str):
            mode_lower = value["mode"].strip().lower()
            if mode_lower == "web":
                use_web = True
            elif mode_lower in {"agent", "deep"}:
                use_agent = True
                use_deep = mode_lower == "deep"

        # Deep requires agent.
        if use_deep and not use_agent:
            use_deep = False

        return SearchMode(useWebSearch=use_web, useAgent=use_agent, useDeepSearch=use_deep)

    return None


class ProviderCircuitSnapshot(BaseModel):
    is_open: bool
    consecutive_failures: int
    opened_for_seconds: Optional[float] = None
    resets_in_seconds: Optional[float] = None


class SearchProviderSnapshot(BaseModel):
    name: str
    available: bool
    healthy: bool
    total_calls: int
    success_count: int
    error_count: int
    success_rate: float
    avg_latency_ms: float
    avg_result_quality: float
    last_error: Optional[str] = None
    last_error_time: Optional[str] = None
    circuit: ProviderCircuitSnapshot


class SearchProvidersResponse(BaseModel):
    providers: List[SearchProviderSnapshot]


class ImagePayload(BaseModel):
    name: Optional[str] = None
    data: str
    mime: Optional[str] = None


class ChatRequest(BaseModel):
    messages: List[Message]
    stream: bool = True
    model: Optional[str] = None
    search_mode: Optional[SearchMode] = None
    agent_id: Optional[str] = None  # optional GPTs-like agent profile id (data/agents.json)
    user_id: Optional[str] = None
    images: Optional[List[ImagePayload]] = None  # Base64 images for multimodal input

    @field_validator("search_mode", mode="before")
    @classmethod
    def _coerce_search_mode(cls, value: Any) -> SearchMode | None:
        return _coerce_search_mode_input(value)


class ResearchRequest(BaseModel):
    query: str
    model: Optional[str] = None
    search_mode: Optional[SearchMode] = None
    agent_id: Optional[str] = None
    user_id: Optional[str] = None
    images: Optional[List[ImagePayload]] = None

    @field_validator("search_mode", mode="before")
    @classmethod
    def _coerce_search_mode(cls, value: Any) -> SearchMode | None:
        return _coerce_search_mode_input(value)


class ChatResponse(BaseModel):
    id: str
    content: str
    role: str = "assistant"
    timestamp: str


class GraphInterruptResumeRequest(BaseModel):
    thread_id: str
    payload: Any
    model: Optional[str] = None
    search_mode: Optional[SearchMode] = None
    agent_id: Optional[str] = None

    @field_validator("search_mode", mode="before")
    @classmethod
    def _coerce_search_mode(cls, value: Any) -> SearchMode | None:
        return _coerce_search_mode_input(value)


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


class AgentsListResponse(BaseModel):
    agents: List[AgentProfile]


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


# ---------------------------------------------------------------------------
# Global Exception Handlers — consistent JSON error responses
# ---------------------------------------------------------------------------
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse as StarletteJSONResponse


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return human-readable validation errors instead of raw Pydantic output."""
    request_id = (request.headers.get("X-Request-ID") or "").strip() or str(uuid.uuid4())[:8]
    errors = []
    for err in exc.errors():
        field = " → ".join(str(loc) for loc in err.get("loc", []))
        errors.append({"field": field, "message": err.get("msg", ""), "type": err.get("type", "")})
    logger.warning(f"Validation error | ID: {request_id} | Errors: {errors}")
    return StarletteJSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "detail": errors,
            "request_id": request_id,
            "timestamp": datetime.now().isoformat(),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Consistent JSON format for all HTTP exceptions."""
    request_id = (request.headers.get("X-Request-ID") or "").strip() or str(uuid.uuid4())[:8]
    return StarletteJSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail if isinstance(exc.detail, str) else "HTTP Error",
            "status_code": exc.status_code,
            "request_id": request_id,
            "timestamp": datetime.now().isoformat(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all handler — never leak stack traces in production."""
    request_id = (request.headers.get("X-Request-ID") or "").strip() or str(uuid.uuid4())[:8]
    logger.error(
        f"Unhandled exception | ID: {request_id} | {type(exc).__name__}: {exc}",
        exc_info=True,
    )
    detail = str(exc) if settings.debug else "An internal server error occurred."
    return StarletteJSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": detail,
            "request_id": request_id,
            "timestamp": datetime.now().isoformat(),
        },
    )


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Weaver Research Agent", "version": "0.1.0"}


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "database": "configured" if settings.database_url else "not configured",
        "version": app.version,
        "uptime_seconds": time.monotonic() - APP_STARTED_AT,
        "timestamp": datetime.now().isoformat(),
    }


# ==================== 鍙栨秷浠诲姟 API ====================


@app.post("/api/chat/cancel/{thread_id}")
async def cancel_chat(thread_id: str, request: Request, payload: CancelRequest | None = None):
    """
    鍙栨秷姝ｅ湪杩涜鐨勮亰澶╀换鍔?
    Args:
        thread_id: 浠诲姟绾跨▼ ID
        request: 鍙€夌殑鍙栨秷鍘熷洜
    """
    _require_thread_owner(request, thread_id)

    reason = payload.reason if payload else "User requested cancellation"
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
            "timestamp": datetime.now().isoformat(),
        }
    else:
        return {
            "status": "not_found",
            "thread_id": thread_id,
            "message": "Task not found or already completed",
        }


def _task_is_visible_to_principal(task_id: str, task_info: Dict[str, Any], principal_id: str) -> bool:
    owner_id = (get_thread_owner(task_id) or "").strip()
    if owner_id:
        return owner_id == principal_id
    metadata = task_info.get("metadata", {})
    if isinstance(metadata, dict):
        meta_user_id = metadata.get("user_id")
        if isinstance(meta_user_id, str) and meta_user_id.strip():
            return meta_user_id.strip() == principal_id
    return False


@app.post("/api/chat/cancel-all")
async def cancel_all_chats(request: Request):
    """鍙栨秷鎵€鏈夋鍦ㄨ繘琛岀殑浠诲姟"""
    logger.info("Cancel all tasks requested")

    reason = "Batch cancellation requested"
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    if internal_key:
        principal_id = (getattr(request.state, "principal_id", "") or "").strip()

        # Cancel only tasks belonging to this principal to avoid cross-user cancellation.
        active = cancellation_manager.get_active_tasks()
        owned_task_ids = [
            task_id
            for task_id, info in active.items()
            if _task_is_visible_to_principal(task_id, info, principal_id)
        ]
        for task_id in owned_task_ids:
            await cancellation_manager.cancel(task_id, reason)
            task = active_streams.pop(task_id, None)
            if task:
                task.cancel()

        cancelled_count = len(owned_task_ids)
    else:
        # 取消所有令牌
        await cancellation_manager.cancel_all(reason)

        # 取消所有异步任务
        cancelled_count = len(active_streams)
        for task in active_streams.values():
            task.cancel()
        active_streams.clear()

    return {
        "status": "all_cancelled",
        "cancelled_count": cancelled_count,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/tasks/active")
async def get_active_tasks(request: Request):
    """Get all active tasks."""
    active_tasks = cancellation_manager.get_active_tasks()

    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    if internal_key:
        principal_id = (getattr(request.state, "principal_id", "") or "").strip()
        active_tasks = {
            task_id: info
            for task_id, info in active_tasks.items()
            if _task_is_visible_to_principal(task_id, info, principal_id)
        }

        # Compute a user-scoped stats payload (avoid leaking global counts).
        stats = {status.value: 0 for status in TaskStatus}
        for info in active_tasks.values():
            st = info.get("status")
            if isinstance(st, str) and st in stats:
                stats[st] += 1
        stats["total"] = len(active_tasks)

        stream_count = sum(
            1
            for thread_id in active_streams.keys()
            if _task_is_visible_to_principal(
                thread_id,
                active_tasks.get(thread_id, {}),
                principal_id,
            )
        )
    else:
        stats = cancellation_manager.get_stats()
        stream_count = len(active_streams)

    return {
        "active_tasks": active_tasks,
        "stats": stats,
        "stream_count": stream_count,
        "timestamp": datetime.now().isoformat(),
    }


# ==================== 娴佸紡浜嬩欢鏍煎紡鍖?====================


async def format_stream_event(event_type: str, data: Any) -> str:
    """
    Format events in Vercel AI SDK Data Stream Protocol format.

    Format: {type}:{json_data}\n
    """
    payload = {"type": event_type, "data": data}
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
        use_deep_prompt = bool(
            search_mode.get("useDeepPrompt", search_mode.get("use_deep_prompt", use_deep))
        )

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
        normalized.append({"name": img.name or "", "mime": img.mime or "", "data": data})
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
async def support_chat(request: Request, payload: SupportChatRequest):
    """Simple customer support chat backed by Mem0 memory."""
    try:
        internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
        principal_id = (getattr(request.state, "principal_id", "") or "").strip()
        user_id = (
            principal_id
            if internal_key and principal_id
            else (payload.user_id or "default_user")
        )
        state = {
            "messages": [
                SystemMessage(content="You are a helpful support assistant."),
                HumanMessage(content=payload.message),
            ],
            "user_id": user_id,
        }
        config = {"configurable": {"thread_id": user_id or "support_default"}}
        # Inject stored memories if present
        store_memories = _store_search(payload.message, user_id=state["user_id"])
        if store_memories:
            state["messages"].insert(
                0,
                SystemMessage(
                    content="Stored memories:\n" + "\n".join(f"- {m}" for m in store_memories)
                ),
            )

        result = support_graph.invoke(state, config=config)
        messages = result.get("messages", [])
        reply = ""
        for msg in reversed(messages):
            if hasattr(msg, "content"):
                reply = msg.content
                break
        if not reply:
            reply = "No response generated."
        _store_add(payload.message, reply, user_id=state["user_id"])
        return SupportChatResponse(content=reply, timestamp=datetime.now().isoformat())
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
    user_id: Optional[str] = None,
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
        metadata={
            "model": model,
            "input_preview": input_text[:100],
            # Used for internal-auth per-user isolation in admin/debug endpoints.
            "user_id": user_id,
        },
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
            "is_cancelled": False,
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

        mem_entries = fetch_memories(query=input_text, user_id=user_id)
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
                "max_revisions": settings.max_revisions,
            },
            "recursion_limit": 50,
        }

        # Send initial status
        yield await format_stream_event(
            "status",
            {"text": "Initializing research agent...", "step": "init", "thread_id": thread_id},
        )

        # Stream graph execution
        async for event in research_graph.astream_events(initial_state, config=config):
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
                    elif tool_event.type == ToolEvent.RESEARCH_NODE_START:
                        yield await format_stream_event("research_node_start", tool_event.data)
                    elif tool_event.type == ToolEvent.RESEARCH_NODE_COMPLETE:
                        yield await format_stream_event("research_node_complete", tool_event.data)
                    elif tool_event.type == ToolEvent.RESEARCH_TREE_UPDATE:
                        yield await format_stream_event("research_tree_update", tool_event.data)
                    elif tool_event.type == ToolEvent.QUALITY_UPDATE:
                        yield await format_stream_event("quality_update", tool_event.data)
                    elif tool_event.type == ToolEvent.SEARCH:
                        yield await format_stream_event("search", tool_event.data)
                except asyncio.QueueEmpty:
                    break

            # Check cancellation status
            if cancel_token.is_cancelled:
                logger.info(f"Stream cancelled for thread {thread_id}")
                yield await format_stream_event(
                    "cancelled", {"message": "Task was cancelled by user", "thread_id": thread_id}
                )
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
                    yield await format_stream_event(
                        "status",
                        {"text": "Checking if clarification is needed...", "step": "clarifying"},
                    )
                elif "planner" in node_name:
                    logger.debug(f"  Planning node started | Thread: {thread_id}")
                    yield await format_stream_event(
                        "status", {"text": "Creating research plan...", "step": "planning"}
                    )
                elif "perform_parallel_search" in node_name or "search" in node_name:
                    logger.debug(f"  Search node started | Thread: {thread_id}")
                    yield await format_stream_event(
                        "status", {"text": "Conducting research...", "step": "researching"}
                    )
                elif "writer" in node_name:
                    logger.debug(f"  Writer node started | Thread: {thread_id}")
                    yield await format_stream_event(
                        "status", {"text": "Synthesizing findings...", "step": "writing"}
                    )
                elif node_name == "agent":
                    logger.debug(f"  Agent node started | Thread: {thread_id}")
                    yield await format_stream_event(
                        "status", {"text": "Running agent (tool-calling)...", "step": "agent"}
                    )

            elif event_type in {"on_chain_end", "on_node_end", "on_graph_end"}:
                output = data_dict.get("output", {}) if isinstance(data_dict, dict) else {}
                metrics.mark_event(event_type, node_name)

                # Extract messages from output
                if isinstance(output, dict):
                    # Interrupt handling
                    interrupts = output.get("__interrupt__")
                    if interrupts:
                        was_interrupted = True
                        yield await format_stream_event(
                            "interrupt",
                            {"thread_id": thread_id, "prompts": _serialize_interrupts(interrupts)},
                        )
                        return

                    messages = output.get("messages", [])
                    if messages:
                        for msg in messages:
                            content = msg.content if hasattr(msg, "content") else str(msg)
                            yield await format_stream_event("message", {"content": content})

                    # Check for completion and final report artifact
                    if output.get("is_complete"):
                        final_report = output.get("final_report", "")
                        if final_report:
                            try:
                                candidates: List[Dict[str, Any]] = []
                                scraped_content = output.get("scraped_content")
                                if isinstance(scraped_content, list):
                                    candidates.extend(scraped_content)
                                raw_sources = output.get("sources")
                                if isinstance(raw_sources, list):
                                    candidates.extend(raw_sources)

                                sources = extract_message_sources(candidates)
                                if sources:
                                    yield await format_stream_event(
                                        "sources", {"items": sources}
                                    )
                            except Exception:
                                pass

                            yield await format_stream_event("completion", {"content": final_report})

                            # Also emit as artifact
                            yield await format_stream_event(
                                "artifact",
                                {
                                    "id": f"report_{datetime.now().timestamp()}",
                                    "type": "report",
                                    "title": "Research Report",
                                    "content": final_report,
                                },
                            )
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
                    yield await format_stream_event(
                        "tool", {"name": "search", "status": "running", "query": query}
                    )
                elif "code" in tool_name.lower():
                    yield await format_stream_event(
                        "tool", {"name": "code_execution", "status": "running"}
                    )

            elif event_type == "on_tool_end":
                tool_name = data_dict.get("name", "unknown")
                output = data_dict.get("output", {})

                yield await format_stream_event("tool", {"name": tool_name, "status": "completed"})

                # Check for artifacts from code execution
                if tool_name == "execute_python_code" and isinstance(output, dict):
                    image_data = output.get("image")

                    if image_data:
                        yield await format_stream_event(
                            "artifact",
                            {
                                "id": f"art_{datetime.now().timestamp()}",
                                "type": "chart",
                                "title": "Generated Visualization",
                                "content": "Chart generated from Python code",
                                "image": image_data,
                            },
                        )
                # Browser screenshots (optional Playwright)
                if tool_name == "browser_screenshot" and isinstance(output, dict):
                    image_data = output.get("image")
                    url = output.get("url", "")
                    if image_data:
                        yield await format_stream_event(
                            "artifact",
                            {
                                "id": f"art_{datetime.now().timestamp()}",
                                "type": "chart",
                                "title": "Browser Screenshot",
                                "content": url or "Screenshot",
                                "image": image_data,
                            },
                        )
                # Sandbox browser tools (E2B + Playwright CDP)
                if tool_name.startswith("sb_browser_") and isinstance(output, dict):
                    image_data = output.get("image")
                    url = output.get("url", "")
                    if isinstance(image_data, str) and image_data.strip():
                        yield await format_stream_event(
                            "artifact",
                            {
                                "id": f"art_{datetime.now().timestamp()}",
                                "type": "chart",
                                "title": f"Sandbox Browser ({tool_name})",
                                "content": url or tool_name,
                                "image": image_data,
                            },
                        )

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
        yield await format_stream_event(
            "done",
            {
                "timestamp": datetime.now().isoformat(),
                "metrics": metrics_registry.get(thread_id).to_dict()
                if metrics_registry.get(thread_id)
                else {},
            },
        )

    except asyncio.CancelledError:
        duration = time.time() - start_time
        metrics_registry.finish(thread_id, cancelled=True)
        logger.info(f"? Agent stream cancelled | Thread: {thread_id} | Duration: {duration:.2f}s")
        yield await format_stream_event(
            "cancelled",
            {"message": "Task was cancelled", "thread_id": thread_id, "duration": duration},
        )

    except Exception as e:
        duration = time.time() - start_time
        cancel_token.mark_failed(str(e))
        metrics_registry.finish(thread_id, cancelled=False)
        logger.error(
            f"? Agent stream error | Thread: {thread_id} | "
            f"Duration: {duration:.2f}s | Error: {str(e)}",
            exc_info=True,
        )
        yield await format_stream_event("error", {"message": str(e)})

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


@app.post("/api/chat/sse")
async def chat_sse(request: Request, payload: ChatRequest):
    """
    Standard SSE chat endpoint.

    This endpoint translates the existing legacy `0:{json}\\n` stream protocol
    into standard SSE frames (`event:` / `data:`) so the frontend can use an
    off-the-shelf SSE parser.
    """
    # Get the last user message (same rule as /api/chat).
    user_messages = [msg for msg in payload.messages if msg.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    last_message = user_messages[-1].content
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    principal_id = (getattr(request.state, "principal_id", "") or "").strip()
    user_id = principal_id if internal_key and principal_id else (payload.user_id or settings.memory_user_id)
    mode_info = _normalize_search_mode(payload.search_mode)
    model = (payload.model or settings.primary_model).strip()
    thread_id = f"thread_{uuid.uuid4().hex}"
    set_thread_owner(thread_id, getattr(request.state, "principal_id", "") or "anonymous")

    async def _sse_generator():
        seq = 0

        # Deterministic failure mode when no API key is configured.
        # We keep this fast and side-effect free (no graph compilation/run).
        if not (settings.openai_api_key or "").strip():
            seq += 1
            yield format_sse_event(
                event="error",
                data={"message": "OPENAI_API_KEY is not configured", "thread_id": thread_id},
                event_id=seq,
            )
            seq += 1
            yield format_sse_event(event="done", data={"thread_id": thread_id}, event_id=seq)
            return

        async for maybe_line in iter_with_sse_keepalive(
            stream_agent_events(
                last_message,
                thread_id=thread_id,
                model=model,
                search_mode=mode_info,
                agent_id=payload.agent_id,
                images=_normalize_images_payload(payload.images),
                user_id=user_id,
            ),
            interval_s=15.0,
        ):
            # Keepalive comments are already SSE frames.
            if maybe_line.startswith(":"):
                yield maybe_line
                continue

            seq += 1
            sse = translate_legacy_line_to_sse(maybe_line, seq=seq)
            if sse:
                yield sse

    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Thread-ID": thread_id,
        },
    )


@app.post("/api/chat")
async def chat(request: Request, payload: ChatRequest):
    """
    Main chat endpoint with streaming support.

    Compatible with Vercel AI SDK useChat hook.
    """
    thread_id = None
    try:
        # Get the last user message
        user_messages = [msg for msg in payload.messages if msg.role == "user"]
        if not user_messages:
            logger.warning("Chat request received with no user messages")
            raise HTTPException(status_code=400, detail="No user message found")

        last_message = user_messages[-1].content
        internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
        principal_id = (getattr(request.state, "principal_id", "") or "").strip()
        user_id = principal_id if internal_key and principal_id else (payload.user_id or settings.memory_user_id)
        mode_info = _normalize_search_mode(payload.search_mode)
        model = (payload.model or settings.primary_model).strip()
        agent_id = (payload.agent_id or "default").strip() or "default"
        agent_profile = get_agent_profile(agent_id) or get_agent_profile("default")

        logger.info("Chat request received")
        logger.info(f"  Model: {model}")
        logger.info(f"  Raw search_mode: {payload.search_mode}")
        logger.info(f"  Normalized mode_info: {mode_info}")
        logger.info(f"  Final mode: {mode_info.get('mode')}")
        logger.info(f"  Stream: {payload.stream}")
        logger.info(f"  Message length: {len(last_message)} chars")
        logger.debug(f"  Message preview: {last_message[:200]}...")

        if payload.stream:
            thread_id = f"thread_{uuid.uuid4().hex}"
            logger.info(f"Starting streaming response | Thread: {thread_id}")
            set_thread_owner(thread_id, principal_id or "anonymous")

            # Return streaming response with thread_id in header for cancellation
            return StreamingResponse(
                stream_agent_events(
                    last_message,
                    thread_id=thread_id,
                    model=model,
                    search_mode=mode_info,
                    agent_id=payload.agent_id,
                    images=_normalize_images_payload(payload.images),
                    user_id=user_id,
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Thread-ID": thread_id,  # ?????????
                },
            )
        else:
            # Non-streaming response (fallback)
            initial_state: AgentState = {
                "input": last_message,
                "images": _normalize_images_payload(payload.images),
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
                "errors": [],
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

            mem_entries = fetch_memories(query=last_message, user_id=user_id)
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
                    "agent_profile": agent_profile.model_dump(mode="json")
                    if agent_profile
                    else None,
                    "user_id": user_id,
                    "allow_interrupts": bool(checkpointer),
                    "tool_approval": settings.tool_approval or False,
                    "human_review": settings.human_review or False,
                    "max_revisions": settings.max_revisions,
                },
                "recursion_limit": 50,
            }
            thread_id = thread_id or f"thread_{uuid.uuid4().hex}"
            metrics = metrics_registry.start(
                thread_id, model=model, route=mode_info.get("mode", "direct")
            )
            result = await research_graph.ainvoke(initial_state, config=config)
            final_report = result.get("final_report", "No response generated")
            add_memory_entry(final_report)
            store_interaction(last_message, final_report)
            _store_add(last_message, final_report, user_id=user_id)
            metrics_registry.finish(thread_id, cancelled=False)

            return ChatResponse(
                id=f"msg_{datetime.now().timestamp()}",
                content=final_report,
                timestamp=datetime.now().isoformat(),
            )

    except Exception as e:
        logger.error(
            f"鉁?Chat error | Thread: {thread_id or 'N/A'} | "
            f"Model: {model if 'model' in locals() else (payload.model if 'payload' in locals() else 'N/A')} | "
            f"Error: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/interrupt/resume")
async def resume_interrupt(request: Request, payload: GraphInterruptResumeRequest):
    """
    Resume a LangGraph execution after an interrupt.
    """
    if not checkpointer:
        raise HTTPException(status_code=400, detail="Interrupts require a checkpointer")

    mode_info = _normalize_search_mode(payload.search_mode)
    model = (payload.model or settings.primary_model).strip()
    agent_id = (payload.agent_id or "default").strip() or "default"
    agent_profile = get_agent_profile(agent_id) or get_agent_profile("default")
    # Fast path: avoid invoking the graph when no checkpoint exists for this thread.
    if not payload.thread_id or not str(payload.thread_id).strip():
        raise HTTPException(status_code=400, detail="thread_id is required")
    _require_thread_owner(request, payload.thread_id)
    existing = checkpointer.get_tuple({"configurable": {"thread_id": payload.thread_id}})
    if not existing:
        raise HTTPException(status_code=404, detail="No checkpoint found for this thread_id")
    config = {
        "configurable": {
            "thread_id": payload.thread_id,
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

    result = await research_graph.ainvoke(Command(resume=payload.payload), config=config)
    interrupts = _serialize_interrupts(result.get("__interrupt__"))
    if interrupts:
        return {"status": "interrupted", "interrupts": interrupts}

    final_report = result.get("final_report", "")
    return ChatResponse(
        id=f"msg_{datetime.now().timestamp()}",
        content=final_report,
        timestamp=datetime.now().isoformat(),
    )


@app.get("/api/mcp/config")
async def get_mcp_config():
    """Return current MCP enable flag, servers config, and loaded tool count."""
    return {
        "enabled": mcp_enabled,
        "servers": mcp_servers_config,
        "loaded_tools": mcp_loaded_tools,
    }


@app.get("/api/search/providers", response_model=SearchProvidersResponse)
async def get_search_providers():
    """Expose multi-search provider availability, health, and circuit-breaker state."""
    orchestrator = get_search_orchestrator()
    providers: List[SearchProviderSnapshot] = []

    for provider in orchestrator.providers:
        circuit = orchestrator.reliability_manager.snapshot(provider.name)
        last_error = provider.stats.last_error
        if last_error:
            try:
                from tools.search.providers import _sanitize_error_message

                last_error = _sanitize_error_message(last_error)
            except Exception:
                pass
        providers.append(
            SearchProviderSnapshot(
                name=provider.name,
                available=bool(provider.is_available()),
                healthy=bool(provider.stats.is_healthy),
                total_calls=int(provider.stats.total_calls),
                success_count=int(provider.stats.success_count),
                error_count=int(provider.stats.error_count),
                success_rate=float(provider.stats.success_rate),
                avg_latency_ms=float(provider.stats.avg_latency_ms),
                avg_result_quality=float(provider.stats.avg_result_quality),
                last_error=last_error,
                last_error_time=provider.stats.last_error_time,
                circuit=ProviderCircuitSnapshot(
                    is_open=bool(circuit.get("is_open", False)),
                    consecutive_failures=int(circuit.get("consecutive_failures", 0) or 0),
                    opened_for_seconds=circuit.get("opened_for_seconds"),
                    resets_in_seconds=circuit.get("resets_in_seconds"),
                ),
            )
        )

    return {"providers": providers}


# ==================== Agents (GPTs-like profiles) ====================


@app.get("/api/agents", response_model=AgentsListResponse)
async def list_agents():
    profiles = load_agents()
    return {"agents": profiles}


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
            cfg = _apply_mcp_thread_id(mcp_servers_config, mcp_thread_id)
            mcp_servers_config = cfg
            tools = await reload_mcp_tools(cfg, enabled=True)
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
async def list_runs(request: Request):
    """List in-memory run metrics (per thread)."""
    runs = metrics_registry.all()
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    if internal_key:
        principal_id = (getattr(request.state, "principal_id", "") or "").strip()
        runs = [
            run
            for run in runs
            if (get_thread_owner(str(run.get("run_id") or "")) or "").strip() == principal_id
        ]
    return {"runs": runs}


class RunEvidenceSummary(BaseModel):
    sources_count: int
    unsupported_claims_count: int
    freshness_ratio_30d: Optional[float] = None
    citation_coverage: Optional[float] = None
    query_coverage_score: Optional[float] = None
    freshness_warning: Optional[str] = None
    claim_verifier_total: Optional[int] = None
    claim_verifier_verified: Optional[int] = None
    claim_verifier_unsupported: Optional[int] = None
    claim_verifier_contradicted: Optional[int] = None


class RunMetricsResponse(BaseModel):
    run_id: str
    model: str
    route: str = ""
    started_at: str
    ended_at: Optional[str] = None
    duration_ms: float
    event_count: int
    nodes_started: Dict[str, int]
    nodes_completed: Dict[str, int]
    errors: List[str]
    cancelled: bool
    evidence_summary: RunEvidenceSummary


def _build_run_evidence_summary(thread_id: str) -> RunEvidenceSummary:
    sources_count = 0
    unsupported_claims_count = 0
    freshness_ratio_30d: Optional[float] = None
    citation_coverage: Optional[float] = None
    query_coverage_score: Optional[float] = None
    freshness_warning: Optional[str] = None
    claim_verifier_total: Optional[int] = None
    claim_verifier_verified: Optional[int] = None
    claim_verifier_unsupported: Optional[int] = None
    claim_verifier_contradicted: Optional[int] = None

    if not checkpointer:
        return RunEvidenceSummary(
            sources_count=sources_count,
            unsupported_claims_count=unsupported_claims_count,
            freshness_ratio_30d=freshness_ratio_30d,
            citation_coverage=citation_coverage,
            query_coverage_score=query_coverage_score,
            freshness_warning=freshness_warning,
            claim_verifier_total=claim_verifier_total,
            claim_verifier_verified=claim_verifier_verified,
            claim_verifier_unsupported=claim_verifier_unsupported,
            claim_verifier_contradicted=claim_verifier_contradicted,
        )

    try:
        from common.session_manager import get_session_manager

        manager = get_session_manager(checkpointer)
        session_state = manager.get_session_state(thread_id)
        if not session_state:
            raise ValueError("session not found")

        artifacts = session_state.deepsearch_artifacts or {}
        if not isinstance(artifacts, dict):
            raise TypeError("deepsearch_artifacts is not a dict")

        sources = artifacts.get("sources", [])
        if isinstance(sources, list):
            sources_count = len(sources)

        claims = artifacts.get("claims", [])
        if isinstance(claims, list):
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                status = (claim.get("status") or "").strip().lower()
                if status in ("unsupported", "contradicted"):
                    unsupported_claims_count += 1

        freshness_summary = artifacts.get("freshness_summary", {})
        if isinstance(freshness_summary, dict):
            ratio = freshness_summary.get("fresh_30_ratio")
            if ratio is not None:
                try:
                    freshness_ratio_30d = float(ratio)
                except (TypeError, ValueError):
                    freshness_ratio_30d = None

        quality_summary = artifacts.get("quality_summary", {})
        if isinstance(quality_summary, dict):
            raw_citation = quality_summary.get("citation_coverage", quality_summary.get("citation_coverage_score"))
            if raw_citation is not None:
                try:
                    citation_coverage = float(raw_citation)
                except (TypeError, ValueError):
                    citation_coverage = None

            raw_query_coverage = quality_summary.get("query_coverage_score")
            if raw_query_coverage is None:
                nested_coverage = quality_summary.get("query_coverage")
                if isinstance(nested_coverage, dict):
                    raw_query_coverage = nested_coverage.get("score")
            if raw_query_coverage is None:
                nested_query_coverage = artifacts.get("query_coverage")
                if isinstance(nested_query_coverage, dict):
                    raw_query_coverage = nested_query_coverage.get("score")
            if raw_query_coverage is not None:
                try:
                    query_coverage_score = float(raw_query_coverage)
                except (TypeError, ValueError):
                    query_coverage_score = None

            freshness_warning_raw = quality_summary.get("freshness_warning")
            if isinstance(freshness_warning_raw, str) and freshness_warning_raw.strip():
                freshness_warning = freshness_warning_raw.strip()

            def _maybe_int(value: Any) -> Optional[int]:
                if value is None:
                    return None
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None

            claim_verifier_total = _maybe_int(quality_summary.get("claim_verifier_total"))
            claim_verifier_verified = _maybe_int(quality_summary.get("claim_verifier_verified"))
            claim_verifier_unsupported = _maybe_int(quality_summary.get("claim_verifier_unsupported"))
            claim_verifier_contradicted = _maybe_int(quality_summary.get("claim_verifier_contradicted"))

    except Exception:
        # Evidence summary is best-effort; never fail the metrics endpoint for this.
        pass

    return RunEvidenceSummary(
        sources_count=sources_count,
        unsupported_claims_count=unsupported_claims_count,
        freshness_ratio_30d=freshness_ratio_30d,
        citation_coverage=citation_coverage,
        query_coverage_score=query_coverage_score,
        freshness_warning=freshness_warning,
        claim_verifier_total=claim_verifier_total,
        claim_verifier_verified=claim_verifier_verified,
        claim_verifier_unsupported=claim_verifier_unsupported,
        claim_verifier_contradicted=claim_verifier_contradicted,
    )


@app.get("/api/runs/{thread_id}", response_model=RunMetricsResponse)
async def get_run_metrics(thread_id: str, request: Request):
    """Get metrics for a specific run/thread."""
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    if internal_key:
        principal_id = (getattr(request.state, "principal_id", "") or "").strip()
        owner_id = (get_thread_owner(thread_id) or "").strip()
        if owner_id and principal_id and owner_id != principal_id:
            raise HTTPException(status_code=403, detail="Forbidden")

    metrics = metrics_registry.get(thread_id)
    if not metrics:
        raise HTTPException(status_code=404, detail="Run not found")
    payload = metrics.to_dict()
    return RunMetricsResponse(
        **payload,
        evidence_summary=_build_run_evidence_summary(thread_id),
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
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


# ==================== Tracing API ====================


@app.get("/api/traces/{thread_id}")
async def get_traces(thread_id: str, request: Request):
    """
    Get traces for a thread.

    Returns the latest trace with full span tree.
    """
    from common.tracing import get_trace

    if not settings.enable_tracing:
        raise HTTPException(status_code=400, detail="Tracing is not enabled")

    _require_thread_owner(request, thread_id)

    trace = get_trace(thread_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"No traces found for thread {thread_id}")

    return trace


@app.get("/api/traces/{thread_id}/summary")
async def get_trace_summary(thread_id: str, request: Request):
    """
    Get trace summary for a thread.

    Returns high-level statistics: token counts, durations, node breakdown.
    """
    from common.tracing import get_trace_summary as _get_summary

    if not settings.enable_tracing:
        raise HTTPException(status_code=400, detail="Tracing is not enabled")

    _require_thread_owner(request, thread_id)

    summary = _get_summary(thread_id)
    if not summary:
        raise HTTPException(status_code=404, detail=f"No traces found for thread {thread_id}")

    return summary


@app.get("/api/traces/{thread_id}/all")
async def get_all_traces(thread_id: str, request: Request):
    """
    Get all traces for a thread.

    Returns list of all stored traces (up to buffer limit).
    """
    from common.tracing import get_all_traces as _get_all

    if not settings.enable_tracing:
        raise HTTPException(status_code=400, detail="Tracing is not enabled")

    _require_thread_owner(request, thread_id)

    traces = _get_all(thread_id)
    return {"thread_id": thread_id, "count": len(traces), "traces": traces}


# ==================== Report Export API ====================


class ExportRequest(BaseModel):
    """Export request for generating reports in various formats."""
    format: str = "html"  # html, pdf, docx
    title: Optional[str] = None


@app.get("/api/export/{thread_id}")
async def export_report_endpoint(
    thread_id: str,
    request: Request,
    format: str = "html",
    title: Optional[str] = None,
    template: str = "default",
):
    """
    Export a research report for a given thread.

    Args:
        thread_id: Thread ID to export report for
        format: Output format (html, pdf, docx)
        title: Optional custom title for the report
        template: Template style (default, academic, business, minimal)
    """
    if not checkpointer:
        raise HTTPException(status_code=400, detail="No checkpointer configured")

    try:
        _require_thread_owner(request, thread_id)
        config = {"configurable": {"thread_id": thread_id}}
        checkpoint = checkpointer.get_tuple(config)
        if not checkpoint:
            raise HTTPException(status_code=404, detail=f"No checkpoint found for thread {thread_id}")

        state = checkpoint.checkpoint.get("channel_values", {})
        final_report = state.get("final_report", "")
        if not final_report:
            raise HTTPException(status_code=404, detail="No report found for this thread")

        scraped = state.get("scraped_content", [])
        extracted_sources = []
        try:
            if isinstance(scraped, list):
                extracted_sources = extract_message_sources(scraped)
        except Exception:
            extracted_sources = []

        source_urls = [
            s.get("url")
            for s in extracted_sources
            if isinstance(s, dict) and isinstance(s.get("url"), str) and s.get("url")
        ]

        report_title = title or "Research Report"
        format_lower = format.lower().strip()

        if format_lower == "json":
            deepsearch_artifacts = state.get("deepsearch_artifacts", {}) or {}
            if not isinstance(deepsearch_artifacts, dict):
                deepsearch_artifacts = {}

            sources_payload = deepsearch_artifacts.get("sources")
            if not isinstance(sources_payload, list):
                sources_payload = extracted_sources

            claims_payload = deepsearch_artifacts.get("claims")
            if not isinstance(claims_payload, list):
                claims_payload = []
                try:
                    from agent.workflows.claim_verifier import ClaimVerifier

                    scraped_list = scraped if isinstance(scraped, list) else []
                    passages_payload = deepsearch_artifacts.get("passages")
                    passages_list = passages_payload if isinstance(passages_payload, list) else None

                    if (scraped_list or passages_list) and isinstance(final_report, str) and final_report.strip():
                        verifier = ClaimVerifier()
                        checks = verifier.verify_report(
                            final_report,
                            scraped_list,
                            passages=passages_list,
                        )
                        claims_payload = [
                            {
                                "claim": c.claim,
                                "status": c.status.value,
                                "evidence_urls": c.evidence_urls,
                                "evidence_passages": c.evidence_passages,
                                "score": c.score,
                                "notes": c.notes,
                            }
                            for c in checks
                        ]
                except Exception:
                    claims_payload = []

            quality_payload = deepsearch_artifacts.get("quality_summary")
            if not isinstance(quality_payload, dict):
                quality_payload = state.get("quality_summary", {}) or {}
                if not isinstance(quality_payload, dict):
                    quality_payload = {}

            return StarletteJSONResponse(
                status_code=200,
                content={
                    "thread_id": thread_id,
                    "title": report_title,
                    "report": final_report,
                    "sources": sources_payload,
                    "claims": claims_payload,
                    "quality": quality_payload,
                    "exported_at": datetime.now().isoformat(),
                },
                headers={"Content-Disposition": f'attachment; filename="report_{thread_id}.json"'},
            )

        if format_lower == "html":
            from tools.export import export_report as do_export

            html_content = do_export(
                final_report, format="html", title=report_title,
                thread_id=thread_id, sources=source_urls,
            )
            return StreamingResponse(
                iter([html_content.encode("utf-8") if isinstance(html_content, str) else html_content]),
                media_type="text/html",
                headers={"Content-Disposition": f'inline; filename="report_{thread_id}.html"'},
            )

        elif format_lower == "pdf":
            try:
                from tools.export import export_report as do_export

                pdf_bytes = do_export(
                    final_report, format="pdf", title=report_title,
                    thread_id=thread_id, sources=source_urls,
                )
                return StreamingResponse(
                    iter([pdf_bytes if isinstance(pdf_bytes, bytes) else pdf_bytes.encode("utf-8")]),
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="report_{thread_id}.pdf"'},
                )
            except ImportError as e:
                raise HTTPException(status_code=501, detail=f"PDF export requires WeasyPrint: {e}")

        elif format_lower in ("docx", "doc"):
            try:
                from tools.export import export_report as do_export

                docx_bytes = do_export(
                    final_report, format="docx", title=report_title,
                    thread_id=thread_id, sources=source_urls,
                )
                return StreamingResponse(
                    iter([docx_bytes if isinstance(docx_bytes, bytes) else docx_bytes.encode("utf-8")]),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="report_{thread_id}.docx"'},
                )
            except ImportError as e:
                raise HTTPException(status_code=501, detail=f"DOCX export requires python-docx: {e}")

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}. Use html, pdf, or docx.")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export error for thread {thread_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/export/templates")
async def list_export_templates():
    """List available export templates."""
    return {
        "templates": [
            {
                "id": "default",
                "name": "Default",
                "description": "Standard research report format with Weaver branding",
            },
            {
                "id": "academic",
                "name": "Academic",
                "description": "Formal serif font style for research papers with proper citations",
            },
            {
                "id": "business",
                "name": "Business",
                "description": "Professional business report with gradient header and modern layout",
            },
            {
                "id": "minimal",
                "name": "Minimal",
                "description": "Clean, distraction-free formatting focused on content",
            },
        ]
    }


# ==================== RAG Document API ====================


def _rag_collection_for_request(request: Request) -> str:
    """
    Resolve the Chroma collection name for RAG documents.

    Hybrid behavior:
    - Default/dev (internal auth disabled): single shared collection
    - Enterprise internal (internal auth enabled): per-principal isolated collection
    """
    base = (getattr(settings, "rag_collection_name", "") or "weaver_documents").strip() or "weaver_documents"
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    if not internal_key:
        return base

    principal_id = (getattr(request.state, "principal_id", "") or "").strip() or "internal"
    suffix = hashlib.sha256(principal_id.encode("utf-8")).hexdigest()[:12]
    return f"{base}__u_{suffix}"


@app.post("/api/documents/upload")
async def upload_document(request: Request, file: UploadFile = File(...)):
    """
    Upload a document to the RAG knowledge base.

    Supports PDF, DOCX, TXT, MD files.
    """
    if not settings.rag_enabled:
        raise HTTPException(status_code=400, detail="RAG is not enabled. Set rag_enabled=True in settings.")

    # Validate file size (max 50MB)
    MAX_FILE_SIZE = 50 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB.")

    # Validate file extension
    ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "txt", "md", "csv"}
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '.{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    try:
        from tools.rag.rag_tool import get_rag_tool

        rag = get_rag_tool(collection_name=_rag_collection_for_request(request))
        if rag is None:
            raise HTTPException(status_code=500, detail="Failed to initialize RAG tool")

        result = rag.add_document(content=content, filename=file.filename)

        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Upload failed"))

        return {
            "success": True,
            "filename": file.filename,
            "chunks": result.get("chunks", 0),
            "message": f"Document '{file.filename}' uploaded successfully with {result.get('chunks', 0)} chunks",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents/list")
async def list_documents(request: Request, limit: int = 100):
    """
    List all documents in the RAG knowledge base.
    """
    if not settings.rag_enabled:
        raise HTTPException(status_code=400, detail="RAG is not enabled.")

    try:
        from tools.rag.rag_tool import get_rag_tool

        rag = get_rag_tool(collection_name=_rag_collection_for_request(request))
        if rag is None:
            raise HTTPException(status_code=500, detail="Failed to initialize RAG tool")

        documents = rag.list_documents(limit=limit)
        count = rag.count()

        return {
            "total_chunks": count,
            "documents": documents,
        }

    except Exception as e:
        logger.error(f"List documents error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/documents/{source:path}")
async def delete_document(source: str, request: Request):
    """
    Delete a document from the RAG knowledge base by source path.
    """
    if not settings.rag_enabled:
        raise HTTPException(status_code=400, detail="RAG is not enabled.")

    try:
        from tools.rag.rag_tool import get_rag_tool

        rag = get_rag_tool(collection_name=_rag_collection_for_request(request))
        if rag is None:
            raise HTTPException(status_code=500, detail="Failed to initialize RAG tool")

        result = rag.delete_document(source)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Delete failed"))

        return {"success": True, "message": f"Document '{source}' deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete document error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/documents/search")
async def search_documents(request: Request, query: str, n_results: int = 5):
    """
    Search the RAG knowledge base.
    """
    if not settings.rag_enabled:
        raise HTTPException(status_code=400, detail="RAG is not enabled.")

    try:
        from tools.rag.rag_tool import get_rag_tool

        rag = get_rag_tool(collection_name=_rag_collection_for_request(request))
        if rag is None:
            raise HTTPException(status_code=500, detail="Failed to initialize RAG tool")

        results = rag.search(query, n_results=n_results)

        return {
            "query": query,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Search documents error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Sessions API ====================


class SessionSummary(BaseModel):
    thread_id: str
    status: str
    topic: str
    created_at: str
    updated_at: str
    route: str
    has_report: bool
    revision_count: int
    message_count: int


class SessionsListResponse(BaseModel):
    count: int
    sessions: List[SessionSummary]


class EvidenceSource(BaseModel):
    title: str = ""
    url: str
    rawUrl: Optional[str] = None
    domain: Optional[str] = None
    provider: Optional[str] = None
    publishedDate: Optional[str] = None


class EvidenceClaimEvidence(BaseModel):
    url: str
    snippet_hash: Optional[str] = None
    quote: Optional[str] = None
    heading_path: Optional[List[str]] = None


class EvidenceClaim(BaseModel):
    claim: str
    status: str
    evidence_urls: List[str] = []
    evidence_passages: List[EvidenceClaimEvidence] = []
    score: float = 0.0
    notes: str = ""


class FetchedPageItem(BaseModel):
    url: str
    raw_url: str
    method: str
    text: Optional[str] = None
    title: Optional[str] = None
    published_date: Optional[str] = None
    retrieved_at: Optional[str] = None
    markdown: Optional[str] = None
    http_status: Optional[int] = None
    error: Optional[str] = None
    attempts: int = 1


class EvidencePassageItem(BaseModel):
    url: str
    text: str
    start_char: int
    end_char: int
    heading: Optional[str] = None
    heading_path: Optional[List[str]] = None
    page_title: Optional[str] = None
    retrieved_at: Optional[str] = None
    method: Optional[str] = None
    quote: Optional[str] = None
    snippet_hash: Optional[str] = None


class EvidenceResponse(BaseModel):
    sources: List[EvidenceSource] = []
    claims: List[EvidenceClaim] = []
    quality_summary: Dict[str, Any] = {}
    fetched_pages: List[FetchedPageItem] = []
    passages: List[EvidencePassageItem] = []


@app.get("/api/sessions", response_model=SessionsListResponse)
async def list_sessions(
    request: Request,
    limit: int = 50,
    status: Optional[str] = None,
):
    """
    List all research sessions.

    Args:
        limit: Maximum sessions to return
        status: Filter by status (pending, running, completed, cancelled)
    """
    if not checkpointer:
        raise HTTPException(status_code=400, detail="No checkpointer configured")

    try:
        from common.session_manager import get_session_manager

        manager = get_session_manager(checkpointer)
        internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
        user_filter = None
        if internal_key:
            user_filter = (getattr(request.state, "principal_id", "") or "").strip() or "internal"
        sessions = manager.list_sessions(limit=limit, status_filter=status, user_id_filter=user_filter)

        return {
            "count": len(sessions),
            "sessions": [s.to_dict() for s in sessions],
        }

    except Exception as e:
        logger.error(f"List sessions error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/{thread_id}")
async def get_session(thread_id: str, request: Request):
    """
    Get session info by thread ID.
    """
    if not checkpointer:
        raise HTTPException(status_code=400, detail="No checkpointer configured")

    try:
        from common.session_manager import get_session_manager

        manager = get_session_manager(checkpointer)

        internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
        if internal_key:
            principal_id = (getattr(request.state, "principal_id", "") or "").strip()
            session_state = manager.get_session_state(thread_id)
            if session_state and isinstance(session_state.state, dict):
                owner = session_state.state.get("user_id")
                if isinstance(owner, str) and owner.strip() and owner.strip() != principal_id:
                    raise HTTPException(status_code=403, detail="Forbidden")

        session = manager.get_session(thread_id)

        if not session:
            raise HTTPException(status_code=404, detail=f"Session not found: {thread_id}")

        return session.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get session error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/{thread_id}/state")
async def get_session_state(thread_id: str, request: Request):
    """
    Get full session state snapshot.
    """
    if not checkpointer:
        raise HTTPException(status_code=400, detail="No checkpointer configured")

    try:
        from common.session_manager import get_session_manager

        manager = get_session_manager(checkpointer)
        state = manager.get_session_state(thread_id)

        if not state:
            raise HTTPException(status_code=404, detail=f"Session not found: {thread_id}")

        internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
        if internal_key:
            principal_id = (getattr(request.state, "principal_id", "") or "").strip()
            owner = state.state.get("user_id") if isinstance(state.state, dict) else None
            if isinstance(owner, str) and owner.strip() and owner.strip() != principal_id:
                raise HTTPException(status_code=403, detail="Forbidden")

        return state.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get session state error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/{thread_id}/evidence", response_model=EvidenceResponse)
async def get_session_evidence(thread_id: str, request: Request):
    """
    Get evidence artifacts (sources + claims + quality summary) for a session.
    """
    if not checkpointer:
        raise HTTPException(status_code=400, detail="No checkpointer configured")

    try:
        from common.session_manager import get_session_manager

        manager = get_session_manager(checkpointer)
        session_state = manager.get_session_state(thread_id)
        if not session_state:
            raise HTTPException(status_code=404, detail=f"Session not found: {thread_id}")

        internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
        if internal_key:
            principal_id = (getattr(request.state, "principal_id", "") or "").strip()
            owner = session_state.state.get("user_id") if isinstance(session_state.state, dict) else None
            if isinstance(owner, str) and owner.strip() and owner.strip() != principal_id:
                raise HTTPException(status_code=403, detail="Forbidden")

        artifacts = session_state.deepsearch_artifacts or {}
        if not isinstance(artifacts, dict):
            artifacts = {}

        sources = artifacts.get("sources", [])
        claims = artifacts.get("claims", [])
        quality_summary = artifacts.get("quality_summary", {})
        fetched_pages = artifacts.get("fetched_pages", [])
        passages = artifacts.get("passages", [])

        return {
            "sources": sources if isinstance(sources, list) else [],
            "claims": claims if isinstance(claims, list) else [],
            "quality_summary": quality_summary if isinstance(quality_summary, dict) else {},
            "fetched_pages": fetched_pages if isinstance(fetched_pages, list) else [],
            "passages": passages if isinstance(passages, list) else [],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get session evidence error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class SessionResumeRequest(BaseModel):
    """Request to resume a session."""
    additional_input: Optional[str] = None
    update_state: Optional[Dict[str, Any]] = None


@app.post("/api/sessions/{thread_id}/resume")
async def resume_session(
    thread_id: str,
    request: Request,
    payload: SessionResumeRequest | None = None,
):
    """
    Resume a paused or cancelled research session.
    """
    if not checkpointer:
        raise HTTPException(status_code=400, detail="No checkpointer configured")

    try:
        from common.session_manager import get_session_manager

        _require_thread_owner(request, thread_id)

        manager = get_session_manager(checkpointer)

        # Check if session can be resumed
        can_resume, reason = manager.can_resume(thread_id)
        if not can_resume:
            raise HTTPException(status_code=400, detail=reason)

        # Get current state
        state = manager.get_session_state(thread_id)
        if not state:
            raise HTTPException(status_code=404, detail=f"Session not found: {thread_id}")

        restored_state = manager.build_resume_state(
            thread_id=thread_id,
            additional_input=payload.additional_input if payload else None,
            update_state=payload.update_state if payload else None,
        )
        if restored_state is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {thread_id}")

        deepsearch_artifacts = restored_state.get("deepsearch_artifacts", {}) or {}
        quality_summary = deepsearch_artifacts.get("quality_summary", {}) if isinstance(
            deepsearch_artifacts, dict
        ) else {}
        queries = deepsearch_artifacts.get("queries", []) if isinstance(
            deepsearch_artifacts, dict
        ) else []
        query_coverage = deepsearch_artifacts.get("query_coverage", {}) if isinstance(
            deepsearch_artifacts, dict
        ) else {}
        freshness_summary = deepsearch_artifacts.get("freshness_summary", {}) if isinstance(
            deepsearch_artifacts, dict
        ) else {}
        if not isinstance(query_coverage, dict):
            query_coverage = {}
        if not isinstance(freshness_summary, dict):
            freshness_summary = {}
        query_coverage_score = query_coverage.get("score")
        if query_coverage_score is not None:
            try:
                query_coverage_score = float(query_coverage_score)
            except (TypeError, ValueError):
                query_coverage_score = None
        if query_coverage_score is None and isinstance(quality_summary, dict):
            nested_coverage = quality_summary.get("query_coverage")
            if isinstance(nested_coverage, dict):
                query_coverage_score = nested_coverage.get("score")
            if query_coverage_score is None:
                query_coverage_score = quality_summary.get("query_coverage_score")
            if query_coverage_score is not None:
                try:
                    query_coverage_score = float(query_coverage_score)
                except (TypeError, ValueError):
                    query_coverage_score = None
        freshness_warning = ""
        if isinstance(quality_summary, dict):
            freshness_warning = str(quality_summary.get("freshness_warning") or "")

        # Resume the graph execution
        # Note: Actual resumption depends on the graph implementation
        # This returns info for the client to continue via SSE
        return {
            "success": True,
            "thread_id": thread_id,
            "status": "ready_to_resume",
            "message": f"Session {thread_id} is ready to resume. Use the streaming endpoint with this thread_id.",
            "current_state": {
                "route": state.state.get("route"),
                "revision_count": state.state.get("revision_count", 0),
                "has_report": bool(state.state.get("final_report")),
                "has_deepsearch_artifacts": bool(deepsearch_artifacts),
                "deepsearch_queries": len(queries) if isinstance(queries, list) else 0,
            },
            "deepsearch_resume": {
                "artifacts_restored": bool(deepsearch_artifacts),
                "mode": deepsearch_artifacts.get("mode") if isinstance(deepsearch_artifacts, dict) else None,
                "quality_summary": quality_summary if isinstance(quality_summary, dict) else {},
                "query_coverage_score": query_coverage_score,
                "freshness_warning": freshness_warning,
                "freshness_summary": freshness_summary,
            },
            "resume_state": {
                "route": restored_state.get("route"),
                "revision_count": restored_state.get("revision_count", 0),
                "research_plan_count": len(restored_state.get("research_plan", []) or []),
                "resumed_from_checkpoint": bool(restored_state.get("resumed_from_checkpoint")),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resume session error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/sessions/{thread_id}")
async def delete_session(thread_id: str, request: Request):
    """
    Delete a research session.
    """
    if not checkpointer:
        raise HTTPException(status_code=400, detail="No checkpointer configured")

    try:
        from common.session_manager import get_session_manager

        _require_thread_owner(request, thread_id)

        manager = get_session_manager(checkpointer)
        success = manager.delete_session(thread_id)

        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to delete session: {thread_id}")

        return {
            "success": True,
            "message": f"Session {thread_id} deleted",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete session error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Collaboration API ====================


class ShareRequest(BaseModel):
    """Request to create a share link."""
    permissions: str = "view"
    expires_hours: Optional[int] = 72


class CommentRequest(BaseModel):
    """Request to add a comment."""
    content: str
    author: str = "anonymous"
    message_id: Optional[str] = None


class SessionComment(BaseModel):
    id: str
    thread_id: str
    message_id: Optional[str] = None
    author: str
    content: str
    created_at: str
    updated_at: str


class CommentsResponse(BaseModel):
    comments: List[SessionComment]
    count: int


class SessionVersion(BaseModel):
    id: str
    thread_id: str
    version_number: int
    label: str
    created_at: str
    snapshot_size: int


class VersionsResponse(BaseModel):
    versions: List[SessionVersion]
    count: int


@app.post("/api/sessions/{thread_id}/share")
async def create_share(thread_id: str, request: Request, req: ShareRequest):
    """Create a share link for a session."""
    try:
        _require_thread_owner(request, thread_id)
        from common.collaboration import create_share_link

        link = create_share_link(
            thread_id=thread_id,
            permissions=req.permissions,
            expires_hours=req.expires_hours,
        )
        return {
            "success": True,
            "share": link,
            "url": f"/share/{link['id']}",
        }
    except Exception as e:
        logger.error(f"Create share error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/share/{share_id}")
async def get_share(share_id: str):
    """Get shared session content."""
    try:
        from common.collaboration import get_share_link

        link = get_share_link(share_id)
        if not link:
            raise HTTPException(status_code=404, detail="Share link not found or expired")

        # Get session state if checkpointer available
        session_data = None
        if checkpointer:
            from common.session_manager import get_session_manager

            manager = get_session_manager(checkpointer)
            session = manager.get_session(link["thread_id"])
            if session:
                session_data = {
                    "id": session.thread_id,
                    "title": session.title,
                    "messages": session.messages,
                }

        return {
            "success": True,
            "share": link,
            "session": session_data,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get share error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/share/{share_id}")
async def delete_share(share_id: str):
    """Delete a share link."""
    try:
        from common.collaboration import delete_share_link

        success = delete_share_link(share_id)
        if not success:
            raise HTTPException(status_code=404, detail="Share link not found")
        return {"success": True, "id": share_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete share error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sessions/{thread_id}/comments")
async def add_comment(thread_id: str, request: Request, req: CommentRequest):
    """Add a comment to a session."""
    try:
        _require_thread_owner(request, thread_id)
        from common.collaboration import add_comment

        comment = add_comment(
            thread_id=thread_id,
            content=req.content,
            author=req.author,
            message_id=req.message_id,
        )
        return {"success": True, "comment": comment}
    except Exception as e:
        logger.error(f"Add comment error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/{thread_id}/comments", response_model=CommentsResponse)
async def get_comments(thread_id: str, request: Request, message_id: Optional[str] = None):
    """Get comments for a session."""
    try:
        _require_thread_owner(request, thread_id)
        from common.collaboration import get_comments

        comments = get_comments(thread_id, message_id)
        return {"comments": comments, "count": len(comments)}
    except Exception as e:
        logger.error(f"Get comments error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/{thread_id}/versions", response_model=VersionsResponse)
async def get_versions(thread_id: str, request: Request):
    """Get version history for a session."""
    try:
        _require_thread_owner(request, thread_id)
        from common.collaboration import list_versions

        versions = list_versions(thread_id)
        return {"versions": versions, "count": len(versions)}
    except Exception as e:
        logger.error(f"Get versions error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sessions/{thread_id}/versions")
async def create_version(thread_id: str, request: Request, label: Optional[str] = None):
    """Create a version snapshot of a session."""
    try:
        if not checkpointer:
            raise HTTPException(status_code=400, detail="No checkpointer configured")

        _require_thread_owner(request, thread_id)

        from common.collaboration import save_version
        from common.session_manager import get_session_manager

        manager = get_session_manager(checkpointer)
        session = manager.get_session(thread_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Create snapshot from session state
        state_snapshot = {
            "thread_id": session.thread_id,
            "title": session.title,
            "messages": session.messages,
            "metadata": getattr(session, "metadata", {}),
        }

        version = save_version(thread_id, state_snapshot, label)
        return {"success": True, "version": version}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create version error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sessions/{thread_id}/restore/{version_id}")
async def restore_version(thread_id: str, version_id: str, request: Request):
    """Restore a session from a version snapshot."""
    try:
        _require_thread_owner(request, thread_id)
        from common.collaboration import get_version_snapshot

        snapshot = get_version_snapshot(version_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="Version snapshot not found")

        # Note: Full restoration would require re-initializing the session state
        # For now, just return the snapshot for client-side handling
        return {
            "success": True,
            "snapshot": snapshot,
            "message": "Version snapshot retrieved. Client should handle restoration.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Restore version error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== HITL Interrupt API ====================


class InterruptAction(str, Enum):
    """Actions for interrupt handling."""
    APPROVE = "approve"      # Approve and continue
    MODIFY = "modify"        # Modify state and continue
    REJECT = "reject"        # Reject and stop
    SKIP = "skip"            # Skip this checkpoint


class InterruptResumeRequest(BaseModel):
    """Request to resume from an interrupt point."""
    action: str = "approve"
    modifications: Optional[Dict[str, Any]] = None
    feedback: Optional[str] = None


@app.get("/api/interrupt/{thread_id}/status")
async def get_interrupt_status(thread_id: str, request: Request):
    """
    Get the current interrupt status for a session.

    Returns information about whether the session is paused at an interrupt point.
    """
    if not checkpointer:
        raise HTTPException(status_code=400, detail="No checkpointer configured")

    try:
        _require_thread_owner(request, thread_id)
        config = {"configurable": {"thread_id": thread_id}}
        checkpoint_tuple = checkpointer.get_tuple(config)

        if not checkpoint_tuple:
            raise HTTPException(status_code=404, detail=f"Session not found: {thread_id}")

        state = checkpoint_tuple.checkpoint.get("channel_values", {})
        metadata = getattr(checkpoint_tuple, "metadata", {}) or {}

        # Check if paused at interrupt
        is_interrupted = metadata.get("interrupted", False)
        interrupt_node = metadata.get("interrupt_node", "")

        # Get checkpoint info
        checkpoint_info = {
            "plan": {
                "node": "planner",
                "description": "Research plan generated, awaiting approval",
                "data": {
                    "research_plan": state.get("research_plan", []),
                    "suggested_queries": state.get("suggested_queries", []),
                },
            },
            "sources": {
                "node": "compressor",
                "description": "Sources collected and compressed, awaiting review",
                "data": {
                    "sources_count": len(state.get("scraped_content", [])),
                    "compressed_knowledge": state.get("compressed_knowledge", {}),
                },
            },
            "draft": {
                "node": "writer",
                "description": "Draft report generated, awaiting review",
                "data": {
                    "draft_report": state.get("draft_report", "")[:1000] + "..." if len(state.get("draft_report", "")) > 1000 else state.get("draft_report", ""),
                },
            },
        }

        # Find which checkpoint we're at
        current_checkpoint = None
        for cp_name, cp_info in checkpoint_info.items():
            if cp_info["node"] == interrupt_node:
                current_checkpoint = cp_name
                break

        return {
            "thread_id": thread_id,
            "is_interrupted": is_interrupted,
            "interrupt_node": interrupt_node,
            "checkpoint_name": current_checkpoint,
            "checkpoint_info": checkpoint_info.get(current_checkpoint, {}) if current_checkpoint else {},
            "available_actions": ["approve", "modify", "reject", "skip"] if is_interrupted else [],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get interrupt status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/interrupt/{thread_id}/resume")
async def resume_from_interrupt(thread_id: str, request: Request, payload: InterruptResumeRequest):
    """
    Resume execution from an interrupt point.

    Actions:
    - approve: Continue with current state
    - modify: Apply modifications and continue
    - reject: Stop execution
    - skip: Skip this step and continue
    """
    if not checkpointer:
        raise HTTPException(status_code=400, detail="No checkpointer configured")

    try:
        _require_thread_owner(request, thread_id)
        config = {"configurable": {"thread_id": thread_id}}
        checkpoint_tuple = checkpointer.get_tuple(config)

        if not checkpoint_tuple:
            raise HTTPException(status_code=404, detail=f"Session not found: {thread_id}")

        action = payload.action.lower()

        if action == "reject":
            # Mark session as cancelled
            return {
                "success": True,
                "action": "rejected",
                "message": f"Session {thread_id} execution rejected. Session cancelled.",
            }

        if action == "modify" and payload.modifications:
            # Apply modifications would require updating the checkpoint
            # This is a simplified implementation
            modifications = payload.modifications
            logger.info(f"Modifications requested for {thread_id}: {modifications}")

        # For approve/skip/modify, return info for client to resume via SSE
        return {
            "success": True,
            "action": action,
            "thread_id": thread_id,
            "message": f"Session {thread_id} ready to resume. Use the streaming endpoint to continue.",
            "modifications_applied": action == "modify",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resume from interrupt error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
                detail="ASR service not available. Please configure DASHSCOPE_API_KEY.",
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
            language_hints=request.language_hints or ["zh", "en"],
        )

        if result["success"]:
            return {"success": True, "text": result["text"], "metrics": result.get("metrics", {})}
        else:
            return {"success": False, "text": "", "error": result.get("error", "Unknown error")}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ASR error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"ASR processing error: {str(e)}")


@app.post("/api/asr/upload")
async def recognize_speech_upload(file: UploadFile = File(...), sample_rate: int = 16000):
    """ASR upload endpoint receiving audio file."""
    # Validate file size (max 50MB)
    MAX_AUDIO_SIZE = 50 * 1024 * 1024
    audio_bytes = await file.read()
    if len(audio_bytes) > MAX_AUDIO_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_AUDIO_SIZE // (1024*1024)}MB.")

    # Validate audio format
    VALID_AUDIO_FORMATS = {"wav", "mp3", "m4a", "flac", "ogg", "webm", "pcm"}
    filename = file.filename or "audio.wav"
    format_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
    if format_ext not in VALID_AUDIO_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format '.{format_ext}'. Allowed: {', '.join(VALID_AUDIO_FORMATS)}")

    # Validate sample rate
    if not (8000 <= sample_rate <= 48000):
        raise HTTPException(status_code=400, detail="Sample rate must be between 8000 and 48000 Hz.")

    try:
        asr_service = get_asr_service()

        if not asr_service.enabled:
            raise HTTPException(
                status_code=503,
                detail="ASR service not available. Please configure DASHSCOPE_API_KEY.",
            )

        result = asr_service.recognize_bytes(
            audio_data=audio_bytes,
            format=format_ext,
            sample_rate=sample_rate,
            language_hints=["zh", "en"],
        )

        if result["success"]:
            return {"success": True, "text": result["text"], "metrics": result.get("metrics", {})}
        else:
            return {"success": False, "text": "", "error": result.get("error", "Unknown error")}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ASR upload error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"ASR processing error: {str(e)}")


@app.get("/api/asr/status")
async def get_asr_status():
    """Get ASR service status."""
    asr_service = get_asr_service()
    return {"enabled": asr_service.enabled, "api_key_configured": bool(settings.dashscope_api_key)}


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
                detail="TTS service not available. Please configure DASHSCOPE_API_KEY.",
            )

        result = tts_service.synthesize(text=request.text, voice=request.voice)

        if result["success"]:
            return {
                "success": True,
                "audio": result["audio"],
                "format": result["format"],
                "voice": result["voice"],
            }
        else:
            return {"success": False, "error": result.get("error", "Unknown error")}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS processing error: {str(e)}")


@app.get("/api/tts/voices")
async def get_tts_voices():
    """Get available TTS voices."""
    return {"voices": AVAILABLE_VOICES, "default": "longxiaochun"}


@app.get("/api/tts/status")
async def get_tts_status():
    """Get TTS service status."""
    tts_service = get_tts_service()
    return {"enabled": tts_service.enabled, "api_key_configured": bool(settings.dashscope_api_key)}


@app.post("/api/research")
async def research(request: Request, query: str):
    """
    Dedicated research endpoint for long-running queries.

    Returns streaming response with research progress.
    """
    thread_id = f"thread_{uuid.uuid4().hex}"
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    principal_id = (getattr(request.state, "principal_id", "") or "").strip()
    user_id = principal_id if internal_key and principal_id else settings.memory_user_id
    set_thread_owner(thread_id, principal_id or "anonymous")

    return StreamingResponse(
        stream_agent_events(query, thread_id=thread_id, user_id=user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Thread-ID": thread_id,
        },
    )


@app.post("/api/research/sse")
async def research_sse(request: Request, payload: ResearchRequest):
    """
    Standard SSE research endpoint.

    This endpoint translates the existing legacy `0:{json}\\n` stream protocol
    into standard SSE frames (`event:` / `data:`) so the frontend can use the
    same SSE parser as `/api/chat/sse`.
    """
    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    principal_id = (getattr(request.state, "principal_id", "") or "").strip()
    user_id = principal_id if internal_key and principal_id else (payload.user_id or settings.memory_user_id)
    mode_info = _normalize_search_mode(payload.search_mode)
    model = (payload.model or settings.primary_model).strip()
    thread_id = f"thread_{uuid.uuid4().hex}"
    set_thread_owner(thread_id, principal_id or "anonymous")

    async def _sse_generator():
        seq = 0

        # Deterministic failure mode when no API key is configured.
        # We keep this fast and side-effect free (no graph compilation/run).
        if not (settings.openai_api_key or "").strip():
            seq += 1
            yield format_sse_event(
                event="error",
                data={"message": "OPENAI_API_KEY is not configured", "thread_id": thread_id},
                event_id=seq,
            )
            seq += 1
            yield format_sse_event(event="done", data={"thread_id": thread_id}, event_id=seq)
            return

        async for maybe_line in iter_with_sse_keepalive(
            stream_agent_events(
                query,
                thread_id=thread_id,
                model=model,
                search_mode=mode_info,
                agent_id=payload.agent_id,
                images=_normalize_images_payload(payload.images),
                user_id=user_id,
            ),
            interval_s=15.0,
        ):
            # Keepalive comments are already SSE frames.
            if maybe_line.startswith(":"):
                yield maybe_line
                continue

            seq += 1
            sse = translate_legacy_line_to_sse(maybe_line, seq=seq)
            if sse:
                yield sse

    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Thread-ID": thread_id,
        },
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
        filepath, media_type=media_type, headers={"Cache-Control": "public, max-age=3600"}
    )


@app.get("/api/screenshots")
async def list_screenshots(request: Request, thread_id: Optional[str] = None, limit: int = 50):
    """
    List available screenshots.

    Args:
        thread_id: Optional filter by thread ID
        limit: Maximum number of results
    """
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    if internal_key:
        if not thread_id or not str(thread_id).strip():
            raise HTTPException(status_code=400, detail="thread_id is required")
        _require_thread_owner(request, str(thread_id))

    service = get_screenshot_service()
    screenshots = service.list_screenshots(thread_id=thread_id, limit=limit)

    return {"screenshots": screenshots, "count": len(screenshots), "thread_id": thread_id}


@app.post("/api/screenshots/cleanup")
async def cleanup_screenshots():
    """Cleanup old screenshots."""
    service = get_screenshot_service()
    deleted_count = await service.cleanup_old_screenshots()

    return {
        "status": "completed",
        "deleted_count": deleted_count,
        "timestamp": datetime.now().isoformat(),
    }


# ==================== Tool Events SSE Endpoint ====================


@app.get("/api/events/{thread_id}")
async def stream_tool_events(thread_id: str, request: Request, last_event_id: Optional[str] = None):
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
    _require_thread_owner(request, thread_id)

    async def event_generator():
        cursor = last_event_id or request.headers.get("last-event-id")
        async for event_sse in event_stream_generator(
            thread_id, timeout=300.0, last_event_id=cursor
        ):
            yield event_sse

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ==================== Browser Session Endpoints ====================

_BROWSER_CLOSED_ERROR_FRAGMENTS = (
    "TargetClosedError",
    "Target page, context or browser has been closed",
    "browser has been closed",
    "Browser has been closed",
    "Browser closed",
    "Playwright connection closed",
)


def _looks_like_browser_closed_error(err: Exception) -> bool:
    msg = str(err) or ""
    return any(fragment in msg for fragment in _BROWSER_CLOSED_ERROR_FRAGMENTS)


@app.get("/api/browser/{thread_id}/info")
async def get_browser_session_info(thread_id: str, request: Request):
    """
    Get browser session information including CDP endpoint.

    Returns browser session status and capabilities for real-time viewing.
    """
    _require_thread_owner(request, thread_id)

    result = {
        "active": False,
        "thread_id": thread_id,
        "mode": None,
        "cdp_endpoint": None,
        "current_url": None,
    }

    # Check sandbox browser session first
    try:
        info = await sandbox_browser_sessions.run_async(
            thread_id,
            lambda: sandbox_browser_sessions.get(thread_id).get_info(),
        )
        result["active"] = True
        result["mode"] = "e2b"
        result["cdp_endpoint"] = info.get("cdp_endpoint") if isinstance(info, dict) else None
        result["current_url"] = info.get("url") if isinstance(info, dict) else None
    except Exception:
        pass

    # Check local browser session if sandbox not found
    if not result["active"]:
        try:
            session = browser_sessions.get(thread_id)
            if session and session.current:
                result["active"] = True
                result["mode"] = "local"
                result["current_url"] = session.current.url
        except Exception:
            pass

    return result


@app.post("/api/browser/{thread_id}/screenshot")
async def trigger_browser_screenshot(thread_id: str, request: Request):
    """
    Trigger a manual screenshot capture for the browser session.
    """
    _require_thread_owner(request, thread_id)

    # Try sandbox browser first
    try:

        def _capture():
            session = sandbox_browser_sessions.get(thread_id)
            page = session.get_page()
            try:
                png_bytes = page.screenshot(full_page=True, animations="disabled", caret="hide")
            except TypeError:
                png_bytes = page.screenshot(full_page=True)
            page_url = None
            try:
                page_url = page.url if page else None
            except Exception:
                page_url = None
            return png_bytes, page_url

        try:
            png_bytes, page_url = await sandbox_browser_sessions.run_async(thread_id, _capture)
        except Exception as e:
            if not _looks_like_browser_closed_error(e):
                raise
            # Session got closed (common after some sites); reset and retry once.
            try:
                await sandbox_browser_sessions.run_async(
                    thread_id, lambda: sandbox_browser_sessions.get(thread_id).close()
                )
            except Exception:
                pass
            png_bytes, page_url = await sandbox_browser_sessions.run_async(thread_id, _capture)

        # Save screenshot
        service = get_screenshot_service()
        save_result = await service.save_screenshot(
            image_data=png_bytes,
            action="manual",
            thread_id=thread_id,
            page_url=page_url,
        )

        # Emit screenshot event
        emitter = await get_emitter(thread_id)
        await emitter.emit(
            "tool_screenshot",
            {
                "tool": "manual",
                "action": "manual",
                "url": save_result.get("url"),
                "filename": save_result.get("filename"),
                "mime_type": save_result.get("mime_type"),
                "page_url": page_url,
            },
        )

        return {
            "success": True,
            "screenshot_url": save_result.get("url"),
            "filename": save_result.get("filename"),
        }
    except Exception as e:
        logger.error(f"Failed to capture screenshot: {e}")

    return {"success": False, "error": "No active browser session"}


@app.websocket("/api/browser/{thread_id}/stream")
async def browser_stream_websocket(websocket: WebSocket, thread_id: str):
    """
    WebSocket endpoint for real-time browser frame streaming.

    Uses periodic Playwright screenshots (~5 FPS by default).
    Frames are sent as base64-encoded JPEG images.

    Message format:
        Incoming: {"action": "start" | "stop" | "capture"}
        Outgoing: {"type": "frame", "data": "<base64>", "timestamp": <float>}
                  {"type": "status", "message": "..."}
                  {"type": "error", "message": "..."}
    """
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    if internal_key:
        auth_user_header = (getattr(settings, "auth_user_header", "") or "").strip() or "X-Weaver-User"
        principal_id = (websocket.headers.get(auth_user_header) or "").strip()

        provided = ""
        auth_header = (websocket.headers.get("Authorization") or "").strip()
        if auth_header.lower().startswith("bearer "):
            provided = auth_header[7:].strip()
        if not provided:
            provided = (websocket.headers.get("X-API-Key") or "").strip()

        if not provided or not hmac.compare_digest(provided, internal_key):
            await websocket.close(code=4401)
            return

        if not principal_id:
            await websocket.close(code=4403)
            return

        owner_id = (get_thread_owner(thread_id) or "").strip()
        if owner_id and owner_id != principal_id:
            await websocket.close(code=4403)
            return

        if checkpointer:
            try:
                from common.session_manager import get_session_manager

                manager = get_session_manager(checkpointer)
                session_state = manager.get_session_state(thread_id)
                if session_state and isinstance(session_state.state, dict):
                    persisted_owner = session_state.state.get("user_id")
                    if (
                        isinstance(persisted_owner, str)
                        and persisted_owner.strip()
                        and persisted_owner.strip() != principal_id
                    ):
                        await websocket.close(code=4403)
                        return
            except Exception:
                pass

    await websocket.accept()

    streaming = False
    stream_task: Optional[asyncio.Task] = None

    async def capture_frame(*, quality: int = 70) -> Dict[str, Any]:
        """Capture a single JPEG frame from the sandbox browser session."""
        q = max(1, min(100, int(quality or 70)))

        def _capture():
            session = sandbox_browser_sessions.get(thread_id)
            page = session.get_page()
            try:
                jpg_bytes = page.screenshot(
                    type="jpeg", quality=q, full_page=False, animations="disabled", caret="hide"
                )
            except TypeError:
                jpg_bytes = page.screenshot(type="jpeg", quality=q, full_page=False)
            metadata: Dict[str, Any] = {}
            try:
                metadata["url"] = page.url
            except Exception:
                pass
            try:
                metadata["title"] = page.title() or ""
            except Exception:
                pass
            return jpg_bytes, metadata

        try:
            jpg_bytes, metadata = await sandbox_browser_sessions.run_async(thread_id, _capture)
        except Exception as e:
            if not _looks_like_browser_closed_error(e):
                raise
            # Session got closed; reset and retry once.
            try:
                await sandbox_browser_sessions.run_async(
                    thread_id, lambda: sandbox_browser_sessions.get(thread_id).close()
                )
            except Exception:
                pass
            jpg_bytes, metadata = await sandbox_browser_sessions.run_async(thread_id, _capture)
        return {
            "data": base64.b64encode(jpg_bytes).decode("ascii"),
            "metadata": metadata,
        }

    async def stream_frames(*, quality: int, max_fps: int):
        nonlocal streaming
        interval = 1.0 / max(1, int(max_fps or 5))
        while streaming:
            try:
                frame = await capture_frame(quality=quality)
                await websocket.send_json(
                    {
                        "type": "frame",
                        "data": frame["data"],
                        "timestamp": time.time(),
                        "metadata": frame.get("metadata") or {},
                    }
                )
            except Exception as e:
                streaming = False
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Capture failed: {e}",
                    }
                )
                break
            await asyncio.sleep(interval)

    try:
        await websocket.send_json(
            {
                "type": "status",
                "message": "Connected to browser stream",
                "thread_id": thread_id,
            }
        )

        while True:
            try:
                data = await websocket.receive_json()
                action = data.get("action", "")

                if action == "start":
                    if streaming:
                        await websocket.send_json(
                            {
                                "type": "status",
                                "message": "Screencast already running",
                            }
                        )
                        continue

                    quality = data.get("quality", 70)
                    max_fps = data.get("max_fps", 5)

                    streaming = True
                    stream_task = asyncio.create_task(
                        stream_frames(quality=int(quality or 70), max_fps=int(max_fps or 5))
                    )
                    await websocket.send_json(
                        {
                            "type": "status",
                            "message": "Screencast started",
                            "quality": quality,
                            "max_fps": max_fps,
                        }
                    )

                elif action == "stop":
                    streaming = False
                    if stream_task:
                        stream_task.cancel()
                        stream_task = None
                    await websocket.send_json(
                        {
                            "type": "status",
                            "message": "Screencast stopped",
                        }
                    )

                elif action == "capture":
                    try:
                        frame = await capture_frame(quality=int(data.get("quality", 70) or 70))
                        await websocket.send_json(
                            {
                                "type": "frame",
                                "data": frame["data"],
                                "timestamp": time.time(),
                                "metadata": frame.get("metadata") or {},
                            }
                        )
                    except Exception as e:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": f"Capture failed: {e}",
                            }
                        )

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": str(e),
                    }
                )

    finally:
        streaming = False
        if stream_task:
            stream_task.cancel()
        logger.info(f"Browser stream WebSocket closed for thread {thread_id}")


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
async def create_scheduled_trigger(request: Request, payload: CreateScheduledTriggerRequest):
    """Create a new scheduled trigger with cron expression."""
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    principal_id = (getattr(request.state, "principal_id", "") or "").strip()
    trigger = ScheduledTrigger(
        name=payload.name,
        description=payload.description,
        schedule=payload.schedule,
        agent_id=payload.agent_id,
        task=payload.task,
        task_params=payload.task_params,
        timezone=payload.timezone,
        run_immediately=payload.run_immediately,
        user_id=(principal_id if internal_key else payload.user_id),
        tags=payload.tags,
    )

    manager = get_trigger_manager()
    trigger_id = await manager.add_trigger(trigger)

    return {
        "success": True,
        "trigger_id": trigger_id,
        "trigger": trigger.to_dict(),
    }


@app.post("/api/triggers/webhook")
async def create_webhook_trigger(request: Request, payload: CreateWebhookTriggerRequest):
    """Create a new webhook trigger."""
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    principal_id = (getattr(request.state, "principal_id", "") or "").strip()
    trigger = WebhookTrigger(
        name=payload.name,
        description=payload.description,
        agent_id=payload.agent_id,
        task=payload.task,
        task_params=payload.task_params,
        http_methods=payload.http_methods,
        require_auth=payload.require_auth,
        rate_limit=payload.rate_limit,
        user_id=(principal_id if internal_key else payload.user_id),
        tags=payload.tags,
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
async def create_event_trigger(request: Request, payload: CreateEventTriggerRequest):
    """Create a new event trigger."""
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    principal_id = (getattr(request.state, "principal_id", "") or "").strip()
    trigger = EventTrigger(
        name=payload.name,
        description=payload.description,
        event_type=payload.event_type,
        event_source=payload.event_source,
        event_filters=payload.event_filters,
        agent_id=payload.agent_id,
        task=payload.task,
        task_params=payload.task_params,
        debounce_seconds=payload.debounce_seconds,
        user_id=(principal_id if internal_key else payload.user_id),
        tags=payload.tags,
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
    request: Request,
    trigger_type: Optional[str] = None,
    status: Optional[str] = None,
    user_id: Optional[str] = None,
):
    """List all triggers with optional filtering."""
    manager = get_trigger_manager()

    type_filter = TriggerType(trigger_type) if trigger_type else None
    status_filter = TriggerStatus(status) if status else None
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    if internal_key:
        principal_id = (getattr(request.state, "principal_id", "") or "").strip()
        user_id = principal_id or user_id

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
async def get_trigger(trigger_id: str, request: Request):
    """Get a specific trigger by ID."""
    manager = get_trigger_manager()
    trigger = manager.get_trigger(trigger_id)

    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    if internal_key:
        principal_id = (getattr(request.state, "principal_id", "") or "").strip()
        if trigger.user_id and trigger.user_id != principal_id:
            raise HTTPException(status_code=403, detail="Forbidden")

    return {"trigger": trigger.to_dict()}


@app.delete("/api/triggers/{trigger_id}")
async def delete_trigger(trigger_id: str, request: Request):
    """Delete a trigger."""
    manager = get_trigger_manager()
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    if internal_key:
        principal_id = (getattr(request.state, "principal_id", "") or "").strip()
        trigger = manager.get_trigger(trigger_id)
        if trigger and trigger.user_id and trigger.user_id != principal_id:
            raise HTTPException(status_code=403, detail="Forbidden")
    success = await manager.remove_trigger(trigger_id)

    if not success:
        raise HTTPException(status_code=404, detail="Trigger not found")

    return {"success": True, "message": "Trigger deleted"}


@app.post("/api/triggers/{trigger_id}/pause")
async def pause_trigger(trigger_id: str, request: Request):
    """Pause a trigger."""
    manager = get_trigger_manager()
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    if internal_key:
        principal_id = (getattr(request.state, "principal_id", "") or "").strip()
        trigger = manager.get_trigger(trigger_id)
        if trigger and trigger.user_id and trigger.user_id != principal_id:
            raise HTTPException(status_code=403, detail="Forbidden")
    success = await manager.pause_trigger(trigger_id)

    if not success:
        raise HTTPException(status_code=404, detail="Trigger not found")

    return {"success": True, "message": "Trigger paused"}


@app.post("/api/triggers/{trigger_id}/resume")
async def resume_trigger(trigger_id: str, request: Request):
    """Resume a paused trigger."""
    manager = get_trigger_manager()
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    if internal_key:
        principal_id = (getattr(request.state, "principal_id", "") or "").strip()
        trigger = manager.get_trigger(trigger_id)
        if trigger and trigger.user_id and trigger.user_id != principal_id:
            raise HTTPException(status_code=403, detail="Forbidden")
    success = await manager.resume_trigger(trigger_id)

    if not success:
        raise HTTPException(status_code=404, detail="Trigger not found or not paused")

    return {"success": True, "message": "Trigger resumed"}


@app.get("/api/triggers/{trigger_id}/executions")
async def get_trigger_executions(trigger_id: str, request: Request, limit: int = 50):
    """Get execution history for a trigger."""
    manager = get_trigger_manager()
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()
    if internal_key:
        principal_id = (getattr(request.state, "principal_id", "") or "").strip()
        trigger = manager.get_trigger(trigger_id)
        if trigger and trigger.user_id and trigger.user_id != principal_id:
            raise HTTPException(status_code=403, detail="Forbidden")
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
    internal_key = (getattr(settings, "internal_api_key", "") or "").strip()

    # Extract request data
    body = None
    try:
        body = await request.json()
    except Exception:
        pass

    query_params = dict(request.query_params)
    headers = dict(request.headers)
    auth_header = request.headers.get("Authorization")

    if internal_key:
        provided = ""
        if isinstance(auth_header, str) and auth_header.strip().lower().startswith("bearer "):
            provided = auth_header.strip()[7:].strip()
        if not provided:
            provided = (request.headers.get("X-API-Key") or "").strip()

        internal_ok = bool(provided) and hmac.compare_digest(provided, internal_key)
        if not internal_ok:
            trigger = manager.get_trigger(trigger_id)
            require_auth = bool(getattr(trigger, "require_auth", False)) if trigger else False
            if trigger and not require_auth:
                raise HTTPException(status_code=401, detail="Unauthorized")

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
    import os

    import uvicorn

    port = int(os.getenv("PORT", "8001"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=settings.debug, log_level="info")
