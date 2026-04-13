"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Cutline supports PostgreSQL in production and SQLite for local dev / tests.
    The DATABASE_URL must include an async driver prefix:
      - postgresql+asyncpg://...
      - sqlite+aiosqlite:///./cutline.db
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./cutline.db"
    cors_origins: list[str] = ["http://localhost:3000"]
    admin_token: str = "dev-admin-token"
    game_name: str = "Cutline"


@lru_cache
def get_settings() -> Settings:
    return Settings()
