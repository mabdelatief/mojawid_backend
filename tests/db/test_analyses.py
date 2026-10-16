"""Analyses, warm-up and the purge against the test database, with a fake worker: idempotency on
client_id, the limits, the GPU budget, the stored errors, and that no audio is ever kept."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access.client import identify
from app.api.deps import get_worker
from app.config import Settings, get_settings
from app.db.session import dispose_engine, get_engine
from app.errors import AppError
from app.main import create_app
from app.services.maintenance_service import MaintenanceService
from app.services.warmup_service import WarmupService

INSTALL = "0b8a3f2e-2c1d-4e5f-9a7b-1c2d3e4f5a6b"
OTHER_INSTALL = "7c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f"
HEADERS = {"X-Api-Key": "mojawid-dev-key", "X-Install-Id": INSTALL}
AUDIO = b"RIFF-not-really-audio-MOJAWID-MARKER-" + b"x" * 1000
MANUAL: dict[str, str | int] = {"mode": "manual", "sura": 112, "aya_start": 1, "aya_end": 1}


def result_for(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": params.get("mode", "manual"),
        "text": {"sura": 112, "aya_start": 1, "aya_end": 1, "prefixes": []},
        "duration_s": 3.2,
        "summary": {"mistakes": 0, "uncertain": 0, "exact_match": True},
        "detection": None,
        "path": None,
        "warnings": [],
        "word_times": [],
        "report": {"errors": [], "exact_match": True},
        "engine": {"model_revision": "m", "segmenter_revision": "s", "quran_transcript": "q",
                   "rules": "hafs_shatibiyya"},
        "timings_ms": {"model": 100, "total": 300},
    }  # fmt: skip


@dataclass
class FakeWorker:
    calls: list[dict[str, Any]] = field(default_factory=list)
    bodies: list[bytes] = field(default_factory=list)
    raise_error: AppError | None = None
    delay: float = 0.0
    warms: int = 0

    async def analyze(self, audio: bytes, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(params)
        self.bodies.append(audio)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raise_error is not None:
            raise self.raise_error
        return result_for(params)

    async def warm(self) -> bool:
        self.warms += 1
        return True


@pytest.fixture
async def clean(engine: AsyncEngine) -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE analysis, rate_limit_counter"))
    WarmupService.last_ping = float("-inf")
    yield


def make_client(migrated_database: str, worker: FakeWorker, **limits: Any) -> httpx.AsyncClient:
    settings = Settings(database_url=migrated_database, **limits)
    get_engine(settings)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_worker] = lambda: worker
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def worker() -> FakeWorker:
    return FakeWorker()


@pytest.fixture
async def client(
    migrated_database: str, clean: None, worker: FakeWorker
) -> AsyncIterator[httpx.AsyncClient]:
    await dispose_engine()
    async with make_client(migrated_database, worker) as c:
        yield c
    await dispose_engine()


def params(client_id: uuid.UUID | str, **extra: Any) -> dict[str, Any]:
    return {**MANUAL, "client_id": str(client_id), **extra}


async def post(c: httpx.AsyncClient, client_id: uuid.UUID | str, **kw: Any) -> httpx.Response:
    headers = kw.pop("headers", HEADERS)
    return await c.post(
        "/v1/analyses", params=params(client_id, **kw), content=AUDIO, headers=headers
    )


async def test_analysis_and_replay(client: httpx.AsyncClient, worker: FakeWorker) -> None:
    cid = uuid.uuid4()
    r = await post(client, cid)
    assert r.status_code == 200, r.text
    assert r.json()["text"]["sura"] == 112
    assert worker.bodies == [AUDIO]
    assert "client_id" not in worker.calls[0] and worker.calls[0]["sura"] == 112
    again = await post(client, cid)
    assert again.status_code == 200 and again.json() == r.json()
    assert len(worker.calls) == 1  # a replay never reaches the worker
    got = await client.get(f"/v1/analyses/{cid}", headers=HEADERS)
    assert got.status_code == 200 and got.json() == r.json()


async def test_concurrent_sends_run_once(client: httpx.AsyncClient, worker: FakeWorker) -> None:
    worker.delay = 0.3
    cid = uuid.uuid4()
    a, b = await asyncio.gather(post(client, cid), post(client, cid))
    assert sorted([a.status_code, b.status_code]) == [200, 409]
    conflict = a if a.status_code == 409 else b
    assert conflict.json()["error"]["code"] == "analysis_in_progress"
    assert len(worker.calls) == 1


async def test_running_shows_202_and_a_stale_claim_is_taken_over(
    client: httpx.AsyncClient, worker: FakeWorker, engine: AsyncEngine
) -> None:
    cid = uuid.uuid4()
    install_hash = await _install_hash(client, engine)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO analysis (install_hash, client_id, status) VALUES (:h, :c, 'running')"
            ),
            {"h": install_hash, "c": cid},
        )
    r = await client.get(f"/v1/analyses/{cid}", headers=HEADERS)
    assert (r.status_code, r.json()) == (202, {"status": "running"})
    assert (await post(client, cid)).status_code == 409  # fresh claim: still running
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE analysis SET updated_at = now() - interval '10 minutes'"))
    assert (await post(client, cid)).status_code == 200  # its worker call died: run it
    assert len(worker.calls) == 1


async def _install_hash(client: httpx.AsyncClient, engine: AsyncEngine) -> str:
    """This install's stored hash (the dev identity secret, as the app computes it)."""
    peer = "127.0.0.1"
    return identify(Settings(), HEADERS["X-Api-Key"], INSTALL, peer, {}).install_hash


async def test_a_final_error_is_kept_a_passing_one_is_not(
    client: httpx.AsyncClient, worker: FakeWorker
) -> None:
    cid = uuid.uuid4()
    worker.raise_error = AppError("audio_unreadable", "Could not read the recording.", 422)
    assert (await post(client, cid)).json()["error"]["code"] == "audio_unreadable"
    worker.raise_error = None
    again = await post(client, cid)
    assert (again.status_code, again.json()["error"]["code"]) == (422, "audio_unreadable")
    got = await client.get(f"/v1/analyses/{cid}", headers=HEADERS)
    assert (got.status_code, got.json()["error"]["code"]) == (422, "audio_unreadable")
    assert len(worker.calls) == 1

    cid = uuid.uuid4()
    worker.raise_error = AppError("analysis_timeout", "Took too long.", 504)
    assert (await post(client, cid)).status_code == 504
    assert (await client.get(f"/v1/analyses/{cid}", headers=HEADERS)).status_code == 404
    worker.raise_error = None
    assert (await post(client, cid)).status_code == 200  # simply sent again


async def test_results_belong_to_their_install(client: httpx.AsyncClient) -> None:
    cid = uuid.uuid4()
    assert (await post(client, cid)).status_code == 200
    other = {**HEADERS, "X-Install-Id": OTHER_INSTALL}
    r = await client.get(f"/v1/analyses/{cid}", headers=other)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "analysis_not_found")
    assert (await client.get(f"/v1/analyses/{uuid.uuid4()}", headers=HEADERS)).status_code == 404


@pytest.mark.parametrize(
    ("query", "status", "code"),
    [
        ({"aya_start": 1, "aya_end": 7, "sura": 2}, 400, "too_many_ayat"),
        ({"client_id": "not-a-uuid"}, 422, "invalid_request"),
    ],
)
async def test_bad_requests(
    client: httpx.AsyncClient, worker: FakeWorker, query: dict[str, Any], status: int, code: str
) -> None:
    r = await client.post(
        "/v1/analyses", params={**params(uuid.uuid4()), **query}, content=AUDIO, headers=HEADERS
    )
    assert (r.status_code, r.json()["error"]["code"]) == (status, code)
    missing = await client.post("/v1/analyses", params=MANUAL, content=AUDIO, headers=HEADERS)
    assert missing.status_code == 422
    no_key = await post(client, uuid.uuid4(), headers={"X-Install-Id": INSTALL})
    assert (no_key.status_code, no_key.json()["error"]["code"]) == (401, "invalid_api_key")
    assert worker.calls == []


async def test_too_large(client: httpx.AsyncClient, worker: FakeWorker) -> None:
    r = await client.post(
        "/v1/analyses", params=params(uuid.uuid4()), content=b"\0" * (2 * 1024 * 1024 + 1),
        headers=HEADERS,
    )  # fmt: skip
    assert (r.status_code, r.json()["error"]["code"]) == (413, "audio_too_large")
    assert worker.calls == []


async def test_install_limit_and_gpu_budget(
    migrated_database: str, clean: None, worker: FakeWorker
) -> None:
    await dispose_engine()
    async with make_client(migrated_database, worker, analyses_per_install_hour=2) as c:
        assert [(await post(c, uuid.uuid4())).status_code for _ in range(2)] == [200, 200]
        r = await post(c, uuid.uuid4())
        assert (r.status_code, r.json()["error"]["code"]) == (429, "rate_limited")
        assert int(r.headers["retry-after"]) > 0
    await dispose_engine()
    # the two analyses above used up a budget of 2 for everyone
    async with make_client(migrated_database, worker, analyses_per_day_total=2) as c:
        r = await post(c, uuid.uuid4(), headers={**HEADERS, "X-Install-Id": OTHER_INSTALL})
        assert (r.status_code, r.json()["error"]["code"]) == (503, "analysis_busy")
        assert int(r.headers["retry-after"]) > 0
    await dispose_engine()
    assert len(worker.calls) == 2


async def test_no_audio_is_ever_kept(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    worker_error = uuid.uuid4()
    assert (await post(client, uuid.uuid4())).status_code == 200
    assert (await post(client, worker_error, aya_end=9, sura=2)).status_code == 400
    async with engine.begin() as conn:
        rows = (await conn.execute(text("SELECT t::text FROM analysis t"))).scalars().all()
        counters = (await conn.execute(text("SELECT t::text FROM rate_limit_counter t"))).all()
    dump = " ".join(rows) + " ".join(str(c) for c in counters)
    assert rows and "MOJAWID-MARKER" not in dump and INSTALL not in dump


async def test_warmup(client: httpx.AsyncClient, worker: FakeWorker) -> None:
    first = await client.post("/v1/warmup", headers=HEADERS)
    assert (first.status_code, first.json()) == (202, {"pinged": True})
    second = await client.post("/v1/warmup", headers=HEADERS)
    assert second.json() == {"pinged": False}  # pinged moments ago
    await asyncio.sleep(0.05)
    assert worker.warms == 1
    assert (await client.post("/v1/warmup")).status_code == 401


async def test_warmup_limit(migrated_database: str, clean: None, worker: FakeWorker) -> None:
    await dispose_engine()
    async with make_client(migrated_database, worker, warmups_per_install_hour=2) as c:
        codes = [(await c.post("/v1/warmup", headers=HEADERS)).status_code for _ in range(3)]
    await dispose_engine()
    assert codes == [202, 202, 429]


async def test_purge(engine: AsyncEngine, clean: None) -> None:
    now = datetime.now(UTC)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO analysis (install_hash, client_id, status, created_at) VALUES "
                "('h', :old, 'done', :then), ('h', :new, 'done', :now)"
            ),
            {
                "old": uuid.uuid4(),
                "new": uuid.uuid4(),
                "then": now - timedelta(hours=25),
                "now": now,
            },
        )
        await conn.execute(
            text(
                "INSERT INTO rate_limit_counter (key, window_start, count) VALUES "
                "('old', :then, 1), ('new', :now, 1)"
            ),
            {"then": now - timedelta(days=3), "now": now},
        )
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as session:
        purged = await MaintenanceService(session, Settings()).purge(now)
    assert (purged.analyses, purged.counters) == (1, 1)
    async with engine.begin() as conn:
        assert await conn.scalar(text("SELECT count(*) FROM analysis")) == 1
        assert await conn.scalar(text("SELECT count(*) FROM rate_limit_counter")) == 1
