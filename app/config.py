"""Runtime settings for the API, loaded from MOJAWID_* environment variables (and .env)."""

from functools import lru_cache
from typing import ClassVar, Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "testing", "production"]
LogFormat = Literal["console", "json"]

_DEV_API_KEY = "mojawid-dev-key"
_DEV_IDENTITY_SECRET = "mojawid-dev-identity-secret"
_DEV_WORKER_TOKEN = "mojawid-dev-worker-token"


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

    # --- Text ---
    # Most ayat a reciter may choose in manual mode (auto mode is limited by the 60 s recording).
    max_ayat_manual: int = 6

    # --- The analysis worker (dev: this laptop's GPU; production: a Modal Server) ---
    worker_url: str = "http://127.0.0.1:8200"
    worker_token: str = _DEV_WORKER_TOKEN
    worker_connect_timeout_s: float = 5.0
    # how long one analysis may take once the worker has the recording; never retried after it
    worker_read_timeout_s: float = 60.0
    # how long to keep retrying while the worker starts (connection refused, 502/503/504)
    worker_retry_window_s: float = 90.0
    # the worker counts as warm this long after it last answered (under Modal's scale-down)
    worker_warm_window_s: float = 240.0

    # --- Analyses ---
    analysis_result_ttl_hours: int = 24
    analysis_stale_after_s: int = 300  # a claim older than this was left by a worker that died
    analyses_per_install_hour: int = 30
    analyses_per_install_day: int = 200
    analyses_per_ip_hour: int = 120
    analyses_per_day_total: int = 5000  # the GPU budget, all users together
    warmups_per_install_hour: int = 20
    warmups_per_ip_hour: int = 60
    purge_interval_s: int = 3600

    # --- Bad-result reports (the only audio ever stored, with consent) ---
    # A private Linode bucket with its own key, limited to it. Unset: reports answer 503.
    reports_bucket: str = ""
    reports_endpoint: str = "https://eu-central-1.linodeobjects.com"
    reports_region: str = "eu-central-1"
    reports_access_key: str = ""
    reports_secret_key: str = ""
    report_upload_window_s: int = 3600  # the audio must follow the report within this time
    report_keep_after_review_days: int = 30  # the rest of a report, after its audio is deleted
    reports_per_install_day: int = 10
    reports_per_ip_day: int = 30

    # --- Recordings: every one kept while in closed testing (app/recordings/) ---
    recordings_dir: str = "~/.local/share/mojawid-recordings"
    recordings_page_size: int = 50
    # The admin page (/admin): HTTP Basic against an argon2 hash
    # (`python -m app.reports.hash_password`). No hash: the page doesn't exist.
    admin_user: str = "admin"
    admin_password_hash: str = ""

    @property
    def reports_configured(self) -> bool:
        return bool(self.reports_bucket and self.reports_access_key and self.reports_secret_key)

    @model_validator(mode="after")
    def _production_secrets(self) -> "Settings":
        """Refuse to start in production with a dev key or secret."""
        if self.environment == "production":
            if not self.api_keys or _DEV_API_KEY in self.api_keys.values():
                raise ValueError("MOJAWID_API_KEYS must be set (no dev key) in production")
            if self.identity_secret == _DEV_IDENTITY_SECRET:
                raise ValueError("MOJAWID_IDENTITY_SECRET must be set in production")
            if self.worker_token == _DEV_WORKER_TOKEN:
                raise ValueError("MOJAWID_WORKER_TOKEN must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings (cached)."""
    return Settings()
