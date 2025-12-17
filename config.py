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
