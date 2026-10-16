"""Runtime settings for the API, loaded from MOJAWID_* environment variables (and .env)."""

from functools import lru_cache
from typing import ClassVar, Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "testing", "production"]
LogFormat = Literal["console", "json"]

_DEV_API_KEY = "mojawid-dev-key"
_DEV_IDENTITY_SECRET = "mojawid-dev-identity-secret"


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

    # --- Access (no accounts: an app key per platform + a random install id) ---
    # {"android": "...", "ios": "...", "web": "..."}. The key ships inside the app, so it only
    # keeps out casual callers; the per-install and per-IP limits are the real protection.
    api_keys: dict[str, str] = {"dev": _DEV_API_KEY}
    # Install ids and IPs are stored only as HMACs under this secret.
    identity_secret: str = _DEV_IDENTITY_SECRET
    # Forwarding headers (CF-Connecting-IP, X-Forwarded-For) are believed only from these peers.
    trusted_proxy_networks: tuple[str, ...] = ("127.0.0.0/8", "::1/128", "10.0.0.0/8")
    cors_origins: tuple[str, ...] = ("*",)

    # --- Reciters ---
    audio_base_url: str = "https://verseaudiofiles.eu-central-1.linodeobjects.com/"
    default_reciter: str = "husary"
    max_timing_ayat: int = 20

    @model_validator(mode="after")
    def _production_secrets(self) -> "Settings":
        """Refuse to start in production with a dev key or secret."""
        if self.environment == "production":
            if not self.api_keys or _DEV_API_KEY in self.api_keys.values():
                raise ValueError("MOJAWID_API_KEYS must be set (no dev key) in production")
            if self.identity_secret == _DEV_IDENTITY_SECRET:
                raise ValueError("MOJAWID_IDENTITY_SECRET must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings (cached)."""
    return Settings()
