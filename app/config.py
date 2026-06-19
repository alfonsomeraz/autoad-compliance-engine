"""Application configuration loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings.

    Values come from environment variables (or a local .env file). The
    Anthropic key is optional so DB-only operations (migrations, seeding,
    rule-engine tests) run without it.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = Field(
        default="postgresql+psycopg2://autoad:autoad@localhost:5432/autoad_dev",
        alias="DATABASE_URL",
    )
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Model selection — Sonnet for quality, Haiku for cheap/high-volume passes.
    llm_model_generation: str = Field(
        default="claude-sonnet-4-6", alias="LLM_MODEL_GENERATION"
    )
    llm_model_extraction: str = Field(
        default="claude-sonnet-4-6", alias="LLM_MODEL_EXTRACTION"
    )
    llm_model_extraction_cheap: str = Field(
        default="claude-haiku-4-5-20251001", alias="LLM_MODEL_EXTRACTION_CHEAP"
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
