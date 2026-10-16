"""Worker settings, from MOJAWID_WORKER_* environment variables."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_TOKEN = "mojawid-dev-worker-token"


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="MOJAWID_WORKER_", case_sensitive=False, extra="ignore"
    )

    environment: str = "local"
    # The API sends this as `Authorization: Bearer …`; nobody else may call the worker.
    token: str = _DEV_TOKEN
    device: str | None = None  # None: CUDA when available

    @model_validator(mode="after")
    def _production_token(self) -> "WorkerSettings":
        if self.environment == "production" and self.token == _DEV_TOKEN:
            raise ValueError("MOJAWID_WORKER_TOKEN must be set in production")
        return self


@lru_cache
def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()
