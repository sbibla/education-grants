from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    database_url: str = "sqlite:///../data/grants.db"
    anthropic_api_key: str = ""
    extract_model: str = "claude-sonnet-5-5"
    triage_model: str = "claude-haiku-5-5"
    search_provider: str = "anthropic"  # anthropic | tavily | brave
    search_api_key: str = ""
    batch_size: int = 10
    default_org_id: int = 1
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
