"""The hourly purge: analyses past their day, and rate-limit counters whose window ended over a
day ago (the longest window is a day). Runs from the API lifespan; deletes are idempotent, so
several API processes running it is harmless.

    .venv/bin/python -m app.maintenance        # once, by hand
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.repositories.analysis_repo import AnalysisRepo
from app.repositories.rate_limit_repo import RateLimitRepo

logger = logging.getLogger("mojawid.maintenance")

COUNTER_KEEP = timedelta(days=2)  # a day-long window that started up to a day ago, plus a day


@dataclass(frozen=True)
class Purged:
    analyses: int
    counters: int


class MaintenanceService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def purge(self, now: datetime | None = None) -> Purged:
        moment = now or datetime.now(UTC)
        ttl = timedelta(hours=self.settings.analysis_result_ttl_hours)
        analyses = await AnalysisRepo(self.session).delete_before(moment - ttl)
        counters = await RateLimitRepo(self.session).delete_before(moment - COUNTER_KEEP)
        await self.session.commit()
        return Purged(analyses, counters)


async def purge_forever(maker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    """Purge now and then every `purge_interval_s`, until cancelled (the lifespan ends)."""
    while True:
        try:
            async with maker() as session:
                purged = await MaintenanceService(session, settings).purge()
            logger.info("purge", extra={"analyses": purged.analyses, "counters": purged.counters})
        except Exception as exc:  # a failed purge must never stop the API; try again next hour
            logger.warning("purge failed", extra={"error_type": type(exc).__name__})
        await asyncio.sleep(settings.purge_interval_s)
