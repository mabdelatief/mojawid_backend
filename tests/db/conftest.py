"""Database tests run against a throwaway `mojawid_test` database on the dev Postgres
(`docker compose up -d`), rebuilt from the migrations once per session. They're skipped, with a
reason, when the dev Postgres isn't running."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

REPO = Path(__file__).resolve().parents[2]
TEST_DB_URL = os.environ.get(
    "MOJAWID_TEST_DATABASE_URL",
    "postgresql+asyncpg://mojawid:mojawid@localhost:5452/mojawid_test",
)


def _plain(url: str, database: str) -> str:
    """The asyncpg DSN for `database` on the same server."""
    return make_url(url).set(drivername="postgresql", database=database).render_as_string(False)


async def _recreate_database() -> None:
    name = make_url(TEST_DB_URL).database
    conn = await asyncpg.connect(_plain(TEST_DB_URL, "postgres"))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


def alembic_config() -> Config:
    """Alembic pointed at the test database."""
    config = Config(str(REPO / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_DB_URL)
    return config


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[str]:
    """A fresh test database at the migration head."""
    try:
        asyncio.run(_recreate_database())
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"dev Postgres not reachable ({type(exc).__name__}): docker compose up -d")
    command.upgrade(alembic_config(), "head")
    yield TEST_DB_URL


@pytest.fixture(scope="session")
async def engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_database)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session whose work is rolled back after each test."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        # create_savepoint: the session never ends the outer transaction, even after an error.
        maker = async_sessionmaker(
            bind=conn,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        async with maker() as s:
            yield s
        await trans.rollback()
