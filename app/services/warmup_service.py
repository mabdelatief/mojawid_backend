"""Warm-up: the app calls it when the Record screen opens, so the worker (scaled to zero on
Modal, 15–40 s to start) is up by the time the recording arrives. It answers at once; the ping
runs in the background, at most once per `warmup_interval_s` per API process."""

import asyncio
import logging
import math
import time
from collections.abc import Callable
from typing import ClassVar, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.access.client import Client
from app.config import Settings
from app.contracts.analysis import WarmupAccepted
from app.errors import AppError
from app.services.rate_limit_service import Limit, RateLimitService

logger = logging.getLogger("mojawid.warmup")

HOUR = 3600


class Warmable(Protocol):
    async def warm(self) -> bool: ...


async def _ping(worker: Warmable) -> None:
    try:
        ready = await worker.warm()
        logger.info("worker warm-up", extra={"ready": ready})
    except AppError as exc:
        logger.warning("worker warm-up failed", extra={"error_code": exc.code})


class WarmupService:
    last_ping: ClassVar[float] = -math.inf  # per process
    _tasks: ClassVar[set["asyncio.Task[None]"]] = set()  # held so they aren't collected

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        worker: Warmable,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.session = session
        self.settings = settings
        self.worker = worker
        self.clock = clock

    async def warm(self, client: Client) -> WarmupAccepted:
        s = self.settings
        await RateLimitService.for_session(self.session).check([
            Limit(f"warmup:install:{client.install_hash}", s.warmups_per_install_hour, HOUR),
            Limit(f"warmup:ip:{client.ip_hash}", s.warmups_per_ip_hour, HOUR),
        ])  # fmt: skip
        now = self.clock()
        if now - WarmupService.last_ping < s.warmup_interval_s:
            return WarmupAccepted(pinged=False)
        WarmupService.last_ping = now
        task = asyncio.create_task(_ping(self.worker))
        WarmupService._tasks.add(task)
        task.add_done_callback(WarmupService._tasks.discard)
        return WarmupAccepted(pinged=True)
