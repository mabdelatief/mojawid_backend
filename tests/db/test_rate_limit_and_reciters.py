"""Against the test database: the rate-limit counter under concurrency, and the reciter routes
end to end."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.config import Settings
from app.db.session import dispose_engine, get_engine
from app.main import create_app
from app.repositories.rate_limit_repo import RateLimitRepo

HEADERS = {"X-Api-Key": "mojawid-dev-key", "X-Install-Id": "0b8a3f2e-2c1d-4e5f-9a7b-1c2d3e4f5a6b"}


async def test_concurrent_increments_are_exact(engine: AsyncEngine) -> None:
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    window = datetime(2026, 1, 1, tzinfo=UTC)

    async def one() -> int:
        async with maker() as session:
            count = await RateLimitRepo(session).increment("concurrency-test", window)
            await session.commit()
            return count

    counts = await asyncio.gather(*(one() for _ in range(50)))
    assert sorted(counts) == list(range(1, 51))
    async with maker() as session:
        assert await RateLimitRepo(session).delete_before(datetime(2026, 1, 2, tzinfo=UTC)) >= 1
        await session.commit()


@pytest.fixture(scope="module")
async def seeded(engine: AsyncEngine) -> AsyncIterator[None]:
    """One offered reciter with 1:1–1:3, one hidden reciter."""
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE recitation CASCADE"))
        await conn.execute(
            text(
                "INSERT INTO recitation (slug, name_ar, name_en, style, bucket_prefix, "
                "file_pattern, timing_source, offered) VALUES "
                "('husary', 'الحصري', 'Husary', 'murattal', 'Husary_64kbps/', "
                "'{surah:03d}{ayah:03d}.mp3', 'test', true), "
                "('hidden', 'x', 'x', 'mujawwad', 'X/', 'x', 'test', false)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO recitation_ayah_timing (recitation_id, surah, ayah, segments) "
                "SELECT id, 1, a, ARRAY[[0, 0, 0, 500], [1, 2, 510, 900]] FROM recitation, "
                "generate_series(1, 3) a WHERE slug = 'husary'"
            )
        )
    yield
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE recitation CASCADE"))


@pytest.fixture
async def client(migrated_database: str, seeded: None) -> AsyncIterator[httpx.AsyncClient]:
    await dispose_engine()
    get_engine(Settings(database_url=migrated_database))
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await dispose_engine()


async def test_list_shows_only_offered(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/reciters", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["default"] == "husary"
    assert [x["slug"] for x in body["reciters"]] == ["husary"]
    assert body["reciters"][0]["audio_url_template"].endswith(
        "/Husary_64kbps/{surah:03d}{ayah:03d}.mp3"
    )
    assert r.headers["cache-control"].startswith("public")


async def test_timings(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/reciters/husary/timings?surah=1&from=2&to=3", headers=HEADERS)
    assert r.status_code == 200
    ayat = r.json()["ayat"]
    assert [a["ayah"] for a in ayat] == [2, 3]
    assert ayat[0]["audio_url"].endswith("/Husary_64kbps/001002.mp3")
    assert ayat[0]["segments"] == [[0, 0, 0, 500], [1, 2, 510, 900]]


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/v1/reciters/hidden/timings?surah=1&from=1&to=1", 404, "not_found"),
        ("/v1/reciters/nope/timings?surah=1&from=1&to=1", 404, "not_found"),
        ("/v1/reciters/husary/timings?surah=1&from=3&to=4", 400, "invalid_text_selection"),
        ("/v1/reciters/husary/timings?surah=1&from=3&to=2", 400, "invalid_text_selection"),
        ("/v1/reciters/husary/timings?surah=1&from=1&to=21", 400, "too_many_ayat"),
        ("/v1/reciters/husary/timings?surah=115&from=1&to=1", 422, "invalid_request"),
    ],
)
async def test_timings_errors(client: httpx.AsyncClient, path: str, status: int, code: str) -> None:
    r = await client.get(path, headers=HEADERS)
    assert (r.status_code, r.json()["error"]["code"]) == (status, code)


async def test_key_required(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/reciters", headers={"X-Install-Id": HEADERS["X-Install-Id"]})
    assert (r.status_code, r.json()["error"]["code"]) == (401, "invalid_api_key")
