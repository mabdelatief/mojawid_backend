"""Warm-up: the app calls it when the Record screen opens, so the worker (scaled to zero on
Modal, 15–40 s to start) is up by the time the recording arrives. It answers at once:
"warm" when the worker answered within `worker_warm_window_s` (no ping is sent), else
"warming", with one background ping per API process at a time."""

import asyncio
import logging
from typing import ClassVar, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.access.client import Client
from app.config import Settings
from app.contracts.analysis import WarmupState
from app.errors import AppError
from app.services.rate_limit_service import Limit, RateLimitService

logger = logging.getLogger("mojawid.warmup")

HOUR = 3600


class Warmable(Protocol):
    async def warm(self) -> bool: ...

    def is_warm(self, window_s: float) -> bool: ...


async def _ping(worker: Warmable) -> None:
    try:
        ready = await worker.warm()
        logger.info("worker warm-up", extra={"ready": ready})
    except AppError as exc:
        logger.warning("worker warm-up failed", extra={"error_code": exc.code})


class WarmupService:
    _ping_task: ClassVar["asyncio.Task[None] | None"] = None  # per process; held so it's kept

    def __init__(self, session: AsyncSession, settings: Settings, worker: Warmable) -> None:
        self.session = session
        self.settings = settings
        self.worker = worker

    async def warm(self, client: Client) -> WarmupState:
        s = self.settings
        await RateLimitService.for_session(self.session).check([
            Limit(f"warmup:install:{client.install_hash}", s.warmups_per_install_hour, HOUR),
            Limit(f"warmup:ip:{client.ip_hash}", s.warmups_per_ip_hour, HOUR),
        ])  # fmt: skip
        if self.worker.is_warm(s.worker_warm_window_s):
            return WarmupState(state="warm")
        task = WarmupService._ping_task
        if task is None or task.done():
            WarmupService._ping_task = asyncio.create_task(_ping(self.worker))
        return WarmupState(state="warming")
