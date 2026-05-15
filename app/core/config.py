"""
app/core/config.py
─────────────────
Single source of truth for all application settings.
Uses pydantic-settings for type-safe, validated env loading.

Design decision: We validate at startup, not lazily. If the app
starts with bad config, it fails fast rather than crashing at runtime
during a request — a critical production practice.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Any

from pydantic import AnyHttpUrl, BeforeValidator, Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_cors(v: Any) -> list[str]:
    """Accept both JSON string and real list from env."""
    if isinstance(v, str):
        return json.loads(v)
    return v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_name: str = "Notes API"
    app_version: str = "1.0.0"
    app_env: str = Field(default="development", pattern="^(development|staging|production)$")
    debug: bool = False
    log_level: str = "INFO"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str  # asyncpg DSN
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False

    @field_validator("database_url", mode="before")
    @classmethod
    def fix_database_url(cls, v: str) -> str:
        """Render gives postgres:// but asyncpg needs postgresql+asyncpg://"""
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl: int = 300

    # ── JWT ───────────────────────────────────────────────────────────────────
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ── Encryption ────────────────────────────────────────────────────────────
    encryption_key: str  # Fernet key, base64-encoded
    encryption_key_version: str = "v1"

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    rate_limit_default: str = "100/minute"
    rate_limit_auth: str = "10/minute"

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: Annotated[list[str], BeforeValidator(_parse_cors)] = ["http://localhost:3000"]
    cors_allow_credentials: bool = True

    # ── Pagination ────────────────────────────────────────────────────────────
    default_page_size: int = 20
    max_page_size: int = 100

    # ── Notes ─────────────────────────────────────────────────────────────────
    max_pinned_notes: int = 5
    max_shared_users_per_note: int = 50

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton — instantiated once per process."""
    return Settings()
