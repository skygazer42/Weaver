from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings."""

    # API Keys
    openai_api_key: str
    tavily_api_key: str = ""
    e2b_api_key: str = ""
    anthropic_api_key: str = ""

    # Database
    database_url: str

    # App Config
    debug: bool = False
    cors_origins: str = "http://localhost:3000"

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


settings = Settings()
