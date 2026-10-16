"""Rate-limit counters."""

from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.rate_limit import RateLimitCounter


class RateLimitRepo:
    """Atomic window counters."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def increment(self, key: str, window_start: datetime) -> int:
        """Add one to the counter and return the new count, in a single statement, so
        concurrent requests can't both read the old value."""
        stmt = (
            insert(RateLimitCounter)
            .values(key=key, window_start=window_start, count=1)
            .on_conflict_do_update(
                index_elements=[RateLimitCounter.key, RateLimitCounter.window_start],
                set_={"count": RateLimitCounter.count + 1},
            )
            .returning(RateLimitCounter.count)
        )
        count = await self.session.scalar(stmt)
        return int(count or 0)

    async def delete_before(self, cutoff: datetime) -> int:
        """Drop counters for windows that started before `cutoff`; returns how many."""
        stmt = (
            delete(RateLimitCounter)
            .where(RateLimitCounter.window_start < cutoff)
            .returning(RateLimitCounter.key)
        )
        return len((await self.session.execute(stmt)).all())
