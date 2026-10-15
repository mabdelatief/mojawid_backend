"""Runtime settings for the API, loaded from MOJAWID_* environment variables (and .env)."""

from functools import lru_cache
from typing import ClassVar, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "testing", "production"]
LogFormat = Literal["console", "json"]


class Settings(BaseSettings):
    """API settings. Every field can be set as MOJAWID_<NAME>."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MOJAWID_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: ClassVar[str] = "Mojawid API"
    app_version: str = "0.1.0"
    environment: Environment = "local"
    # Dev convenience only: adds tracebacks to error logs. Off in production, where an
    # exception message could carry request data.
    debug: bool = False
    docs_enabled: bool = True

    log_level: str = "INFO"
    log_format: LogFormat = "console"
    request_id_header: ClassVar[str] = "X-Request-ID"

    database_url: str = "postgresql+asyncpg://mojawid:mojawid@localhost:5452/mojawid"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 5


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings (cached)."""
    return Settings()
