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

    # If true, the public archive endpoint will return puzzles dated in the
    # future (useful for local preview). On production this should stay False
    # so staged puzzles don't leak before their release time.
    allow_future_archive: bool = False

    # Player-photo storage (manual upload via admin API).
    # photo_upload_dir: filesystem directory where uploads are persisted.
    # photo_url_prefix: URL path that serves them (mounted via StaticFiles).
    photo_upload_dir: str = "./uploads/photos"
    photo_url_prefix: str = "/photos"
    photo_max_bytes: int = 5 * 1024 * 1024  # 5 MB


@lru_cache
def get_settings() -> Settings:
    return Settings()
