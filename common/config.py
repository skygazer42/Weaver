from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings."""

    # API Keys
    openai_api_key: str
    openai_base_url: str = ""
    use_azure: bool = False
    azure_api_key: str = ""
    azure_endpoint: str = ""
    azure_api_version: str = "2025-03-01-preview"
    openai_timeout: int = 60
    openai_extra_body: str = ""  # JSON string for extra OpenAI-compatible params
    tavily_api_key: str = ""
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

    # Database
    database_url: str

    # App Config
    debug: bool = False
    cors_origins: str = "http://localhost:3000"
    interrupt_before_nodes: str = ""  # comma-separated node names for LangGraph interrupts

    # Logging Config
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_file: str = "logs/weaver.log"  # Log file path
    log_max_bytes: int = 10485760  # 10MB
    log_backup_count: int = 5  # Keep 5 backup files
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    enable_file_logging: bool = True  # Enable logging to file
    enable_json_logging: bool = False  # Enable structured JSON logging

    # Model Config
    primary_model: str = "gpt-4o-mini"
    reasoning_model: str = "o1-mini"  # For planning

    # LangGraph Store (long-term memory)
    memory_store_backend: str = "memory"  # memory | postgres | redis
    memory_store_url: str = ""  # connection string for store backend

    # Message trimming (short-term memory)
    trim_messages: bool = False
    trim_messages_keep_first: int = 2
    trim_messages_keep_last: int = 8
    summary_messages: bool = False
    summary_messages_trigger: int = 12   # when messages count exceeds this, summarize middle
    summary_messages_keep_last: int = 4
    summary_messages_model: str = "gpt-4o-mini"
    summary_messages_word_limit: int = 200

    # Concurrency Control (并发控制)
    max_concurrency: int = 5          # 最大并发数
    search_batch_size: int = 3        # 搜索批次大小
    api_rate_limit: float = 0.5       # API 调用间隔（秒）

    # Deepsearch Settings
    deepsearch_max_epochs: int = 3
    deepsearch_query_num: int = 5
    deepsearch_results_per_query: int = 5
    deepsearch_enable_crawler: bool = False  # enable simple fallback crawler
    deepsearch_save_data: bool = False       # save deepsearch run data to disk
    deepsearch_save_dir: str = "eval/deepsearch_data"

    # Prompt Optimization (Prompt 优化)
    prompt_optimizer_model: str = "gpt-4o"  # 用于优化 Prompt 的模型
    prompt_optimization_epochs: int = 3      # 优化迭代轮次
    prompt_optimization_sample_size: int = 50  # 每轮评估样本数

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins string into list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def interrupt_nodes_list(self) -> List[str]:
        """Parse interrupt_before_nodes into list for LangGraph compile."""
        return [
            node.strip() for node in self.interrupt_before_nodes.split(",") if node.strip()
        ]


settings = Settings()
