"""Fixed-window rate limits.

A limit is "at most `max_requests` per `window_seconds` for `key`". Windows are aligned to the
epoch, so every API process agrees on where a window starts. Each check commits its own
increments: a request that's refused still counts, which is what slows a flood down.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.repositories.rate_limit_repo import RateLimitRepo


@dataclass(frozen=True)
class Limit:
    """At most `max_requests` per `window_seconds` for `key` (an HMAC-based key)."""

    key: str
    max_requests: int
    window_seconds: int


class Counter(Protocol):
    """What the service needs from storage (RateLimitRepo, or a fake in unit tests)."""

    async def increment(self, key: str, window_start: datetime) -> int: ...


class Committer(Protocol):
    """The transaction the service owns (an AsyncSession, or a fake in unit tests)."""

    async def commit(self) -> None: ...


def window_start(now: datetime, window_seconds: int) -> datetime:
    """The start of the fixed window containing `now`."""
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % window_seconds, tz=UTC)


class RateLimitService:
    """Counts requests against limits and refuses with 429 once one is over."""

    def __init__(self, tx: Committer, counter: Counter) -> None:
        self.tx = tx
        self.counter = counter

    @classmethod
    def for_session(cls, session: AsyncSession) -> "RateLimitService":
        """The service over a real database session."""
        return cls(session, RateLimitRepo(session))

    async def check(self, limits: Sequence[Limit], now: datetime | None = None) -> None:
        """Count this request against every limit; raise `rate_limited` if any is exceeded."""
        moment = now or datetime.now(UTC)
        retry_after = 0
        for limit in limits:
            start = window_start(moment, limit.window_seconds)
            count = await self.counter.increment(limit.key, start)
            if count > limit.max_requests:
                ends = start + timedelta(seconds=limit.window_seconds)
                retry_after = max(retry_after, int((ends - moment).total_seconds()) + 1)
        await self.tx.commit()
        if retry_after:
            raise AppError(
                "rate_limited",
                "Too many requests; try again later.",
                status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(retry_after)},
            )
