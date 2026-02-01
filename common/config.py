from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)
import os

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    # Python 3.10 fallback
    import tomli as tomllib  # type: ignore
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings

# -----------------------------
# OpenManus-style AppConfig models
# -----------------------------


class LLMSettingsModel(BaseModel):
    model: str
    base_url: str
    api_key: str
    max_tokens: int = 4096
    max_input_tokens: Optional[int] = None
    temperature: float = 1.0
    api_type: str = ""
    api_version: str = ""


class ProxySettings(BaseModel):
    server: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class SearchSettings(BaseModel):
    engine: str = "tavily"
    fallback_engines: List[str] = Field(default_factory=list)
    retry_delay: int = 60
    max_retries: int = 3
    lang: str = "en"
    country: str = "us"


class BrowserSettings(BaseModel):
    headless: bool = False
    disable_security: bool = True
    extra_chromium_args: List[str] = Field(default_factory=list)
    chrome_instance_path: Optional[str] = None
    wss_url: Optional[str] = None
    cdp_url: Optional[str] = None
    proxy: Optional[ProxySettings] = None
    max_content_length: int = 2000


class SandboxSettings(BaseModel):
    use_sandbox: bool = False
    image: str = "python:3.12-slim"
    work_dir: str = "/workspace"
    memory_limit: str = "512m"
    cpu_limit: float = 1.0
    timeout: int = 300
    network_enabled: bool = False


class DaytonaSettings(BaseModel):
    daytona_api_key: str = ""
    daytona_server_url: str = "https://app.daytona.io/api"
    daytona_target: str = "us"
    sandbox_image_name: str = "whitezxj/sandbox:0.1.0"
    sandbox_entrypoint: str = "/usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf"
    VNC_password: str = ""  # Must be set via environment variable


class MCPServerConfig(BaseModel):
    type: str
    url: Optional[str] = None
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)


class MCPSettings(BaseModel):
    servers: Dict[str, MCPServerConfig] = Field(default_factory=dict)


class RunflowSettings(BaseModel):
    use_data_analysis_agent: bool = False


class AppConfig(BaseModel):
    llm: Dict[str, LLMSettingsModel]
    sandbox: Optional[SandboxSettings] = None
    browser_config: Optional[BrowserSettings] = None
    search_config: Optional[SearchSettings] = None
    mcp_config: Optional[MCPSettings] = None
    run_flow_config: Optional[RunflowSettings] = None
    daytona_config: Optional[DaytonaSettings] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8-sig", case_sensitive=False)
    """Application settings."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """
        In local dev, prefer `.env` over process environment variables.

        Many users run multiple projects in the same shell/conda env; a stale
        `OPENAI_API_KEY` in the process env can silently override `.env` and
        lead to confusing auth errors. In prod, keep the standard precedence
        (env vars override dotenv).
        """

        app_env = (os.getenv("APP_ENV") or "").strip().lower()
        debug_raw = (os.getenv("DEBUG") or "").strip().lower()
        debug = debug_raw in {"1", "true", "yes", "y", "on"}

        # If the process explicitly declares production, keep the standard precedence.
        if app_env in {"prod", "production"}:
            return (init_settings, env_settings, dotenv_settings, file_secret_settings)

        # If the process declares dev/debug, prefer dotenv.
        if debug or app_env in {"dev", "debug", "local", "test"}:
            return (init_settings, dotenv_settings, env_settings, file_secret_settings)

        # Heuristic: if a `.env` file exists, assume a local/dev-style run.
        # This avoids confusing cases where a stale process env var overrides `.env`.
        if any(
            candidate.is_file()
            for candidate in (
                Path(".env"),
                Path(__file__).resolve().parent.parent / ".env",
            )
        ):
            return (init_settings, dotenv_settings, env_settings, file_secret_settings)

        return (init_settings, env_settings, dotenv_settings, file_secret_settings)

    # API Keys
    openai_api_key: str = ""
    openai_base_url: str = ""
    use_azure: bool = False
    azure_api_key: str = ""
    azure_endpoint: str = ""
    azure_api_version: str = "2025-03-01-preview"
    openai_timeout: int = 60
    openai_extra_body: str = ""  # JSON string for extra OpenAI-compatible params
    tavily_api_key: str = ""
    # Web search providers (optional; used when SEARCH_ENGINES includes them)
    serper_api_key: str = ""
    serpapi_api_key: str = ""
    bing_api_key: str = ""
    exa_api_key: str = ""
    firecrawl_api_key: str = ""
    google_search_api_key: str = ""  # Google Custom Search API key
    google_search_engine_id: str = ""  # Google Custom Search Engine ID (cx)
    e2b_api_key: str = ""
    anthropic_api_key: str = ""
    dashscope_api_key: str = ""  # 阿里云 DashScope API Key (语音识别)
    mem0_api_key: str = ""
    enable_memory: bool = False
    memory_namespace: str = "default"
    memory_user_id: str = "default_user"
    memory_max_entries: int = 20
    memory_top_k: int = 5
    enable_mcp: bool = False
    mcp_servers: str = ""  # JSON mapping for MultiServerMCPClient
    human_review: bool = False  # require manual approval before final report
    tool_approval: bool = False  # require approval before executing tools
    max_revisions: int = 2

    # Environment
    app_env: str = "dev"  # dev | test | prod
    enable_prometheus: bool = False  # expose /metrics in Prometheus format

    # Database
    database_url: str = ""

    # App Config
    debug: bool = False
    cors_origins: str = "http://localhost:3000,http://localhost:3100"
    interrupt_before_nodes: str = ""  # comma-separated node names for LangGraph interrupts
    app_config_path: str = "config/config.toml"  # Optional TOML config (OpenManus style)
    mcp_config_path: str = "config/mcp.json"  # MCP servers definition (JSON)
    app_config_object: Optional[AppConfig] = None  # populated at runtime if TOML is present

    # Logging Config
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_file: str = "logs/weaver.log"  # Log file path
    log_max_bytes: int = 10485760  # 10MB
    log_backup_count: int = 5  # Keep 5 backup files
    log_format: str = (
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    )
    enable_file_logging: bool = True  # Enable logging to file
    enable_json_logging: bool = False  # Enable structured JSON logging

    # Tracing Config
    enable_tracing: bool = False  # Enable LLM call tracing
    trace_buffer_size: int = 1000  # Max traces to keep in memory
    otlp_endpoint: str = ""  # Optional OTLP exporter endpoint

    # Model Config
    primary_model: str = "deepseek-chat"
    reasoning_model: str = "o1-mini"  # For planning

    # Multi-Model Research Config (Task-specific models)
    planner_model: str = ""  # Model for research planning (defaults to reasoning_model)
    researcher_model: str = ""  # Model for research analysis (defaults to primary_model)
    writer_model: str = ""  # Model for report writing (defaults to primary_model)
    evaluator_model: str = ""  # Model for quality evaluation (defaults to reasoning_model)
    critic_model: str = ""  # Model for URL selection/critique (defaults to reasoning_model)

    # Hierarchical Agent Config
    use_hierarchical_agents: bool = False  # Enable coordinator→planner→researcher→reporter flow

    # Domain Routing Config
    domain_routing_enabled: bool = False  # Enable domain-specific routing and prompts

    # RAG (Retrieval-Augmented Generation) Config
    rag_enabled: bool = False  # Enable local document RAG
    rag_store_path: Optional[str] = None  # Path for persistent vector storage
    rag_collection_name: str = "weaver_documents"  # ChromaDB collection name
    rag_embedding_model: str = "text-embedding-3-small"  # OpenAI embedding model
    rag_chunk_size: int = 1000  # Document chunk size
    rag_chunk_overlap: int = 200  # Overlap between chunks

    # Tree-based Research Config
    tree_exploration_enabled: bool = True  # Enable tree-based deep research
    tree_max_depth: int = 2  # Maximum tree depth (0 = root only)
    tree_max_branches: int = 4  # Maximum children per node
    tree_queries_per_branch: int = 3  # Number of queries per branch
    tree_parallel_branches: int = 3  # Max concurrent branch exploration (0 = sequential)

    # Report Visualization Config
    enable_report_charts: bool = True  # Generate charts from data in reports

    # Human-in-the-Loop (HITL) Config
    hitl_checkpoints: str = ""  # Comma-separated interrupt points: plan,sources,draft,final
    hitl_timeout_seconds: int = 3600  # Max wait time for human review (1 hour)

    # Prompt Config (选择提示词风格)
    prompt_style: str = "enhanced"  # simple | enhanced | custom
    custom_agent_prompt_path: str = ""  # 自定义 agent 提示词文件路径
    custom_writer_prompt_path: str = ""  # 自定义 writer 提示词文件路径
    prompt_pack: str = "deepsearch"  # default prompt pack
    prompt_variant: str = "full"  # full | lite

    # XML Tool Calling Config (Phase 2 - Manus 风格工具调用)
    agent_xml_tool_calling: bool = False  # 启用 XML 工具调用 (Claude 友好)
    agent_native_tool_calling: bool = True  # 启用原生工具调用 (OpenAI 格式)
    agent_execute_tools: bool = True  # 自动执行工具
    agent_auto_continue: bool = False  # 自动续写机制 (finish_reason=tool_calls 时继续)
    agent_max_auto_continues: int = 25  # 最大自动续写次数
    agent_tool_execution_strategy: str = "sequential"  # sequential | parallel

    # LangGraph Store (long-term memory)
    memory_store_backend: str = "memory"  # memory | postgres | redis
    memory_store_url: str = ""  # connection string for store backend

    # Message trimming (short-term memory)
    trim_messages: bool = False
    trim_messages_keep_first: int = 2
    trim_messages_keep_last: int = 8
    summary_messages: bool = False
    summary_messages_trigger: int = 12  # when messages count exceeds this, summarize middle
    summary_messages_keep_last: int = 4
    summary_messages_model: str = "gpt-4o-mini"
    summary_messages_word_limit: int = 200

    # Concurrency Control (并发控制)
    max_concurrency: int = 5  # 最大并发数
    search_batch_size: int = 3  # 搜索批次大小
    api_rate_limit: float = 0.5  # API 调用间隔（秒）

    # Deepsearch Settings
    deepsearch_max_epochs: int = 3
    deepsearch_query_num: int = 5
    deepsearch_results_per_query: int = 5
    deepsearch_enable_crawler: bool = False  # enable simple fallback crawler
    deepsearch_save_data: bool = False  # save deepsearch run data to disk
    deepsearch_save_dir: str = "eval/deepsearch_data"
    deepsearch_use_gap_analysis: bool = True  # use knowledge gap analysis for targeted queries

    # Multi-Search Engine Config
    search_strategy: str = "fallback"  # fallback | parallel | round_robin | best_first
    brave_api_key: str = ""  # Brave Search API key
    serper_api_key: str = ""  # Serper.dev API key
    exa_api_key: str = ""  # Exa.ai API key

    # Real-time Feed Settings
    twitter_bearer_token: str = ""  # Twitter/X API v2 Bearer Token
    twitter_api_key: str = ""  # Twitter API Key (optional)
    twitter_api_secret: str = ""  # Twitter API Secret (optional)
    reddit_client_id: str = ""  # Reddit OAuth client ID
    reddit_client_secret: str = ""  # Reddit OAuth client secret
    reddit_user_agent: str = "Weaver/1.0"  # Reddit API user agent
    hackernews_enabled: bool = True  # HackerNews search (no API key needed)

    # Academic Search Settings
    arxiv_enabled: bool = True  # arXiv search (no API key needed)
    scholar_enabled: bool = True  # Google Scholar (no API key, rate limited)
    semantic_scholar_api_key: str = ""  # Semantic Scholar API key (optional, higher rate)
    pubmed_email: str = ""  # NCBI Entrez email (required for PubMed)
    pubmed_api_key: str = ""  # NCBI API key (optional, higher rate)

    # Crawler
    crawler_headless: bool = True  # True=无头(默认不弹窗)，False=可视化调试
    use_optimized_crawler: bool = False  # 是否启用Playwright优化爬虫，Windows建议默认False

    # Daytona sandbox
    daytona_api_key: str = ""
    daytona_server_url: str = "https://app.daytona.io/api"
    daytona_target: str = "us"
    daytona_image_name: str = "whitezxj/sandbox:0.1.0"
    daytona_entrypoint: str = "/usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf"
    daytona_vnc_password: str = ""  # Must be set via environment variable

    # Sandbox mode: local (E2B), daytona (remote), none (disabled)
    sandbox_mode: str = "local"
    sandbox_template_browser: str = ""  # e2b sandbox browser template ID (e.g., chrome-stable)
    sandbox_allow_internet: bool = True  # allow internet access inside sandbox

    # Tool / middleware controls
    tool_retry: bool = False
    tool_retry_max_attempts: int = 3
    tool_retry_backoff: float = 1.5  # seconds exponential factor
    tool_retry_initial_delay: float = 1.0
    tool_retry_max_delay: float = 60.0
    tool_call_limit: int = 0  # 0 = unlimited per request
    strip_tool_messages: bool = False  # drop ToolMessage from history to save tokens
    context_edit_trigger_tokens: int = 1000
    context_edit_keep_tools: int = 3
    tool_selector: bool = False
    tool_selector_model: str = "gpt-4o-mini"
    tool_selector_max_tools: int = 3
    tool_selector_always_include: str = ""  # comma-separated tool names
    tool_selector_prompt: str = ""
    enable_todo_middleware: bool = False  # enable todo list middleware
    todo_system_prompt: str = ""  # custom system prompt for todo middleware
    todo_tool_description: str = ""  # custom tool description for todo middleware
    enable_browser_use: bool = False  # enable browser_use tool (Playwright-based)
    enable_browser_context_helper: bool = False  # inject browser context prompt if available

    # Tool visibility / events
    emit_tool_events: bool = True  # wrap tools with event emitters for front-end
    tool_whitelist: str = ""  # comma-separated tool names to allow (empty = all)
    tool_blacklist: str = ""  # comma-separated tool names to block

    # Search fallback
    search_engines: str = "tavily"  # comma-separated engines in order

    # Prompt Optimization (Prompt 优化)
    prompt_optimizer_model: str = "gpt-4o"  # 用于优化 Prompt 的模型
    prompt_optimization_epochs: int = 3  # 优化迭代轮次
    prompt_optimization_sample_size: int = 50  # 每轮评估样本数

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins string into list."""
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

        # Dev ergonomics: allow common local frontend ports by default.
        # This keeps the UI working even when CORS_ORIGINS in `.env` is outdated.
        env = (self.app_env or "").strip().lower()
        if (
            self.debug
            or env in {"dev", "debug", "local", "test"}
            or env not in {"prod", "production"}
        ):
            for extra in (
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:3100",
                "http://127.0.0.1:3100",
            ):
                if extra not in origins:
                    origins.append(extra)

        return origins

    @property
    def interrupt_nodes_list(self) -> List[str]:
        """Parse interrupt_before_nodes into list for LangGraph compile."""
        return [node.strip() for node in self.interrupt_before_nodes.split(",") if node.strip()]

    @property
    def tool_selector_always_include_list(self) -> List[str]:
        """Comma separated tool names that must always be kept when selector is on."""
        return [t.strip() for t in self.tool_selector_always_include.split(",") if t.strip()]

    @property
    def tool_whitelist_list(self) -> List[str]:
        """Comma separated tool whitelist."""
        return [t.strip() for t in self.tool_whitelist.split(",") if t.strip()]

    @property
    def tool_blacklist_list(self) -> List[str]:
        """Comma separated tool blacklist."""
        return [t.strip() for t in self.tool_blacklist.split(",") if t.strip()]

    @property
    def search_engines_list(self) -> List[str]:
        """Comma separated ordered search engines."""
        engines = [e.strip() for e in self.search_engines.split(",") if e.strip()]
        if not engines and getattr(self, "app_config_object", None):
            cfg = getattr(self.app_config_object, "search_config", None)
            if cfg:
                engines = [cfg.engine] + list(cfg.fallback_engines or [])
        return engines or ["tavily"]


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_mcp_servers(mcp_path: str) -> Dict[str, MCPServerConfig]:
    """
    Load MCP server configs from JSON (mcp.json or mcp.json.example).
    """
    candidates = [
        _project_root() / mcp_path,
        _project_root() / "config" / "mcp.json.example",
        _project_root() / "docs2" / "config_mcp.json.example",
    ]
    for path in candidates:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                servers = {}
                for sid, scfg in data.get("mcpServers", data.get("servers", {})).items():
                    servers[sid] = MCPServerConfig(
                        type=scfg.get("type", ""),
                        url=scfg.get("url"),
                        command=scfg.get("command"),
                        args=scfg.get("args", []),
                    )
                return servers
            except Exception as e:
                logger.warning(f"Failed to load MCP config from {path}: {e}")
    return {}


@lru_cache()
def load_app_config(config_path: str, mcp_path: str) -> Optional[AppConfig]:
    """
    Load AppConfig from TOML + MCP JSON (compatible with OpenManus config layout).
    """
    root = _project_root()
    primary_path = Path(config_path)
    primary = primary_path if primary_path.is_absolute() else root / config_path
    example = (
        primary.with_suffix(".example.toml")
        if primary.suffix != ".toml"
        else root / "config" / "config.example.toml"
    )
    candidates = [primary, example]
    cfg_file = next((p for p in candidates if p.exists()), None)
    if not cfg_file:
        return None

    data = tomllib.loads(cfg_file.read_text(encoding="utf-8"))
    base_llm = data.get("llm", {}) or {}
    overrides = {k: v for k, v in base_llm.items() if isinstance(v, dict)}

    default_settings = {
        "model": base_llm.get("model", ""),
        "base_url": base_llm.get("base_url", ""),
        "api_key": base_llm.get("api_key", ""),
        "max_tokens": base_llm.get("max_tokens", 4096),
        "max_input_tokens": base_llm.get("max_input_tokens"),
        "temperature": base_llm.get("temperature", 1.0),
        "api_type": base_llm.get("api_type", ""),
        "api_version": base_llm.get("api_version", ""),
    }

    llm_dict: Dict[str, LLMSettingsModel] = {}
    if default_settings.get("model"):
        llm_dict["default"] = LLMSettingsModel(**default_settings)
    for name, override in overrides.items():
        merged = {**default_settings, **override}
        if merged.get("model"):
            llm_dict[name] = LLMSettingsModel(**merged)

    browser_cfg = data.get("browser", {}) or {}
    proxy_cfg = browser_cfg.get("proxy") or {}
    proxy = None
    if proxy_cfg.get("server"):
        proxy = ProxySettings(
            server=proxy_cfg.get("server"),
            username=proxy_cfg.get("username"),
            password=proxy_cfg.get("password"),
        )
    browser_settings = None
    if browser_cfg:
        bs_kwargs = {
            k: v
            for k, v in browser_cfg.items()
            if k in BrowserSettings.__annotations__ and v is not None
        }
        if proxy:
            bs_kwargs["proxy"] = proxy
        if bs_kwargs:
            browser_settings = BrowserSettings(**bs_kwargs)

    search_cfg = data.get("search") or {}
    search_settings = SearchSettings(**search_cfg) if search_cfg else None

    sandbox_cfg = data.get("sandbox") or {}
    sandbox_settings = SandboxSettings(**sandbox_cfg) if sandbox_cfg else None

    daytona_cfg = data.get("daytona") or {}
    daytona_settings = DaytonaSettings(**daytona_cfg) if daytona_cfg else None

    mcp_servers = _load_mcp_servers(mcp_path)
    mcp_cfg = data.get("mcp") or {}
    mcp_settings = (
        MCPSettings(servers=mcp_servers or mcp_cfg.get("servers", {}))
        if (mcp_servers or mcp_cfg)
        else None
    )

    runflow_cfg = data.get("runflow") or {}
    runflow_settings = RunflowSettings(**runflow_cfg) if runflow_cfg else None

    if not llm_dict:
        return None

    return AppConfig(
        llm=llm_dict,
        sandbox=sandbox_settings,
        browser_config=browser_settings,
        search_config=search_settings,
        mcp_config=mcp_settings,
        run_flow_config=runflow_settings,
        daytona_config=daytona_settings,
    )


def apply_app_config_overrides(settings: Settings) -> None:
    """
    Merge TOML/JSON app config into BaseSettings values without overriding explicit env values.
    """
    app_cfg = load_app_config(settings.app_config_path, settings.mcp_config_path)
    settings.app_config_object = app_cfg
    if not app_cfg:
        return

    default_llm = app_cfg.llm.get("default")
    if default_llm:
        if not getattr(settings, "openai_api_key", ""):
            settings.openai_api_key = default_llm.api_key
        if not settings.primary_model:
            settings.primary_model = default_llm.model
        if not settings.openai_base_url:
            settings.openai_base_url = default_llm.base_url

    # Search engines
    if not settings.search_engines.strip() and app_cfg.search_config:
        engines = [app_cfg.search_config.engine] + list(
            app_cfg.search_config.fallback_engines or []
        )
        settings.search_engines = ",".join([e for e in engines if e])

    # Daytona
    if app_cfg.daytona_config:
        cfg = app_cfg.daytona_config
        if not settings.daytona_api_key and cfg.daytona_api_key:
            settings.daytona_api_key = cfg.daytona_api_key
        settings.daytona_server_url = settings.daytona_server_url or cfg.daytona_server_url
        settings.daytona_target = settings.daytona_target or cfg.daytona_target
        settings.daytona_image_name = settings.daytona_image_name or cfg.sandbox_image_name
        settings.daytona_entrypoint = settings.daytona_entrypoint or cfg.sandbox_entrypoint
        settings.daytona_vnc_password = settings.daytona_vnc_password or cfg.VNC_password

    # MCP servers
    if not settings.mcp_servers and app_cfg.mcp_config and app_cfg.mcp_config.servers:
        try:
            settings.mcp_servers = json.dumps(
                {k: v.model_dump() for k, v in app_cfg.mcp_config.servers.items()}
            )
        except Exception as e:
            logger.warning(f"Failed to inject MCP servers from app config: {e}")

    # Sandbox switch from TOML
    if (
        app_cfg.sandbox
        and app_cfg.sandbox.use_sandbox is False
        and settings.sandbox_mode == "local"
    ):
        # allow disabling sandbox via config
        settings.sandbox_mode = "none"


settings = Settings()
apply_app_config_overrides(settings)
