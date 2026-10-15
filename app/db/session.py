"""The async engine and session maker, created once per process."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings, get_settings

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """The process-wide engine."""
    global _engine
    if _engine is None:
        resolved = settings or get_settings()
        _engine = create_async_engine(
            resolved.database_url,
            echo=resolved.database_echo,
            pool_pre_ping=True,
            pool_size=resolved.database_pool_size,
            max_overflow=resolved.database_max_overflow,
        )
    return _engine


def get_session_maker(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    """The process-wide session maker (expire_on_commit=False, autoflush=False)."""
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(
            bind=get_engine(settings), expire_on_commit=False, autoflush=False
        )
    return _session_maker


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """A request-scoped session (FastAPI dependency)."""
    async with get_session_maker()() as session:
        yield session


async def dispose_engine() -> None:
    """Close the pool and forget the engine (lifespan shutdown, tests)."""
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_maker = None
