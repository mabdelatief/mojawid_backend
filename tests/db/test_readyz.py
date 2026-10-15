"""Readiness answers once the database does."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from app.config import Settings
from app.db.session import dispose_engine, get_engine
from app.main import create_app


@pytest.fixture
async def client(migrated_database: str) -> AsyncIterator[httpx.AsyncClient]:
    await dispose_engine()
    get_engine(Settings(database_url=migrated_database))
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await dispose_engine()


async def test_readyz(client: httpx.AsyncClient) -> None:
    r = await client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}
