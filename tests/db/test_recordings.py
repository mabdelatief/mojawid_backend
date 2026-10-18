"""Kept recordings (closed testing) against the test database, with a fake worker: every analysis
keeps its audio and outcome, with who made it; any tester lists, reads and plays them; a resend
keeps nothing twice; a failure is kept with its error; the admin page deletes row and file."""

from __future__ import annotations

import base64
import os
import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.deps import get_object_store, get_worker
from app.config import Settings, get_settings
from app.db.session import dispose_engine, get_engine
from app.errors import AppError
from app.main import create_app
from tests.db.test_analyses import AUDIO, HEADERS, FakeWorker, post

PASSWORD = "a long enough password"
ADMIN = {"Authorization": "Basic " + base64.b64encode(f"admin:{PASSWORD}".encode()).decode()}
OTHER = {**HEADERS, "X-Install-Id": "7c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f"}
EMAIL = "m.tester@example.com"
DIR = Path(os.environ["MOJAWID_RECORDINGS_DIR"])


def make_client(db: str, worker: FakeWorker, **over: Any) -> httpx.AsyncClient:
    """The app with a fake worker and no reports bucket (recording reports need none)."""
    settings = Settings(database_url=db, **over)
    get_engine(settings)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_worker] = lambda: worker
    app.dependency_overrides[get_object_store] = lambda: None
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def worker() -> FakeWorker:
    return FakeWorker()


@pytest.fixture
async def client(
    migrated_database: str, engine: AsyncEngine, worker: FakeWorker
) -> AsyncIterator[httpx.AsyncClient]:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE analysis, rate_limit_counter, recording CASCADE"))
    await dispose_engine()
    hashed = PasswordHasher().hash(PASSWORD)
    async with make_client(migrated_database, worker, admin_password_hash=hashed) as c:
        yield c
    await dispose_engine()


async def record(c: httpx.AsyncClient, headers: dict[str, str] = HEADERS, **kw: Any) -> str:
    r = await post(c, uuid.uuid4(), headers={**headers, "Content-Type": "audio/wav"}, **kw)
    assert r.status_code == 200, r.text
    return r.headers["X-Recording-Id"]


async def test_kept_listed_read_and_played(client: httpx.AsyncClient) -> None:
    rid = await record(client, headers={**HEADERS, "Cf-Access-Authenticated-User-Email": EMAIL})
    assert (DIR / f"{rid}.wav").read_bytes() == AUDIO
    page = (await client.get("/v1/recordings", headers=OTHER)).json()  # any tester sees it
    item = page["items"][0]
    assert (item["id"], item["tester"], item["status"]) == (rid, "m.tester", "done")
    assert item["text"] == {"sura": 112, "aya_start": 1, "aya_end": 1}
    assert item["summary"]["exact_match"] is True and page["next_before"] is None
    detail = (await client.get(f"/v1/recordings/{rid}", headers=OTHER)).json()
    assert detail["result"]["duration_s"] == 3.2 and detail["error_message"] is None
    audio = await client.get(f"/v1/recordings/{rid}/audio", headers=OTHER)
    assert (audio.content, audio.headers["content-type"]) == (AUDIO, "audio/wav")
    part = await client.get(f"/v1/recordings/{rid}/audio", headers={**OTHER, "Range": "bytes=0-9"})
    assert (part.status_code, part.content) == (206, AUDIO[:10])


async def test_email_believed_only_from_the_web_front(
    migrated_database: str, worker: FakeWorker
) -> None:
    async with make_client(migrated_database, worker, trusted_proxy_networks=()) as c:
        rid = await record(c, headers={**HEADERS, "Cf-Access-Authenticated-User-Email": EMAIL})
        assert (await c.get(f"/v1/recordings/{rid}", headers=HEADERS)).json()["tester"] is None


def kept_files() -> set[str]:
    return set(os.listdir(DIR))


async def test_a_resend_is_kept_once(client: httpx.AsyncClient) -> None:
    cid, before = uuid.uuid4(), kept_files()
    headers = {**HEADERS, "Content-Type": "audio/wav"}
    first = await post(client, cid, headers=headers)
    again = await post(client, cid, headers=headers)
    assert first.headers["X-Recording-Id"] == again.headers["X-Recording-Id"]
    items = (await client.get("/v1/recordings", headers=HEADERS)).json()["items"]
    assert len(items) == 1
    assert kept_files() - before == {f"{items[0]['id']}.wav"}  # no second file


async def test_a_failure_is_kept_with_its_error(
    client: httpx.AsyncClient, worker: FakeWorker
) -> None:
    worker.raise_error = AppError("audio_unreadable", "The recording could not be read.", 422)
    r = await post(client, uuid.uuid4(), headers={**HEADERS, "Content-Type": "audio/mp4"})
    assert r.status_code == 422
    item = (await client.get("/v1/recordings", headers=HEADERS)).json()["items"][0]
    assert (item["status"], item["error_code"], item["summary"]) == (
        "failed",
        "audio_unreadable",
        None,
    )
    assert (DIR / f"{item['id']}.m4a").read_bytes() == AUDIO


async def test_paging_and_errors(client: httpx.AsyncClient) -> None:
    ids = [await record(client) for _ in range(3)]
    first = (await client.get("/v1/recordings", params={"limit": 2}, headers=HEADERS)).json()
    assert [i["id"] for i in first["items"]] == ids[::-1][:2] and first["next_before"]
    params = {"limit": 2, "before": first["next_before"]}
    rest = (await client.get("/v1/recordings", params=params, headers=HEADERS)).json()
    assert ([i["id"] for i in rest["items"]], rest["next_before"]) == ([ids[0]], None)
    bad = await client.get("/v1/recordings", params={"before": "nope"}, headers=HEADERS)
    assert (bad.status_code, bad.json()["error"]["code"]) == (400, "invalid_cursor")
    missing = await client.get(f"/v1/recordings/{uuid.uuid4()}/audio", headers=HEADERS)
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "recording_not_found")
    assert (await client.get("/v1/recordings")).status_code == 401  # the app key is required


async def test_admin_lists_plays_and_deletes(client: httpx.AsyncClient) -> None:
    rid = await record(client)
    assert (await client.get("/admin/recordings")).status_code == 401
    page = await client.get("/admin/recordings", headers=ADMIN)
    assert page.status_code == 200 and rid in page.text
    played = await client.get(f"/admin/recordings/{rid}/audio", headers=ADMIN)
    assert played.content == AUDIO
    token = re.search(rf'/admin/recordings/{rid}/delete".*?value="([0-9a-f]+)"', page.text, re.S)
    assert token is not None
    bad = await client.post(f"/admin/recordings/{rid}/delete", data={"csrf": "x"}, headers=ADMIN)
    assert bad.status_code == 403
    done = await client.post(
        f"/admin/recordings/{rid}/delete", data={"csrf": token.group(1)}, headers=ADMIN
    )
    assert done.status_code == 303
    assert (await client.get(f"/v1/recordings/{rid}", headers=HEADERS)).status_code == 404
    assert not (DIR / f"{rid}.wav").exists()


# --- reporting a recording's result as wrong (once per recording) -----------------------------

REPORT = {"category": "false_mistake", "note": "the madd was right"}


async def report(
    c: httpx.AsyncClient, rid: str, headers: dict[str, str] = HEADERS
) -> httpx.Response:
    return await c.post(f"/v1/recordings/{rid}/report", json=REPORT, headers=headers)


async def test_reported_once_and_shown_to_everyone(client: httpx.AsyncClient) -> None:
    rid = await record(client)
    first = await report(client, rid, {**OTHER, "Cf-Access-Authenticated-User-Email": EMAIL})
    assert first.status_code == 201, first.text
    shown = first.json()["report"]
    assert (shown["reporter"], shown["category"], shown["note"]) == (
        "m.tester",
        "false_mistake",
        "the madd was right",
    )
    item = (await client.get("/v1/recordings", headers=HEADERS)).json()["items"][0]
    assert item["report"] == shown
    assert (await client.get(f"/v1/recordings/{rid}", headers=HEADERS)).json()["report"] == shown
    again = await report(client, rid)  # anyone else, later
    assert (again.status_code, again.json()["error"]["code"]) == (409, "recording_already_reported")


async def test_two_reports_at_once_one_wins(client: httpx.AsyncClient) -> None:
    import asyncio

    rid = await record(client)
    a, b = await asyncio.gather(report(client, rid), report(client, rid, OTHER))
    assert sorted([a.status_code, b.status_code]) == [201, 409]


async def test_failed_can_be_reported_unknown_cannot(
    client: httpx.AsyncClient, worker: FakeWorker
) -> None:
    worker.raise_error = AppError("ayah_not_recognised", "No ayah was recognised.", 422)
    await post(client, uuid.uuid4(), headers={**HEADERS, "Content-Type": "audio/wav"})
    rid = (await client.get("/v1/recordings", headers=HEADERS)).json()["items"][0]["id"]
    assert (await report(client, rid)).status_code == 201
    missing = await report(client, str(uuid.uuid4()))
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "recording_not_found")


async def test_a_running_recording_cannot_be_reported(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    rid = await record(client)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE recording SET status = 'running' WHERE id = :i"), {"i": rid}
        )
    r = await report(client, rid)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "recording_not_analysed")


async def test_recording_reports_survive_purge_and_review(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.config import Settings
    from app.services.maintenance_service import MaintenanceService

    rid = await record(client)
    report_id = (await report(client, rid)).json()["id"]
    page = await client.get(f"/admin/reports/{report_id}", headers=ADMIN)
    assert page.status_code == 200 and f"/admin/recordings/{rid}/audio" in page.text
    token = re.search(
        r'/reviewed">\s*<input type="hidden" name="csrf" value="([0-9a-f]+)"', page.text
    )
    assert token is not None
    done = await client.post(
        f"/admin/reports/{report_id}/reviewed", data={"csrf": token.group(1)}, headers=ADMIN
    )
    assert done.status_code == 303
    assert (DIR / f"{rid}.wav").exists()  # «reviewed» never deletes a kept recording
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await MaintenanceService(session, Settings()).purge(datetime.now(UTC) + timedelta(days=90))
    item = (await client.get(f"/v1/recordings/{rid}", headers=HEADERS)).json()
    assert item["report"] is not None  # still reported, so it can't be reported again


async def test_deleting_the_recording_deletes_its_report(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    rid = await record(client)
    report_id = (await report(client, rid)).json()["id"]
    page = await client.get("/admin/recordings", headers=ADMIN)
    assert f"/admin/reports/{report_id}" in page.text  # the «reported» tag links to it
    token = re.search(rf'/admin/recordings/{rid}/delete".*?value="([0-9a-f]+)"', page.text, re.S)
    assert token is not None
    await client.post(
        f"/admin/recordings/{rid}/delete", data={"csrf": token.group(1)}, headers=ADMIN
    )
    async with engine.connect() as conn:
        left = await conn.scalar(
            text("SELECT count(*) FROM report WHERE id = :i"), {"i": report_id}
        )
    assert left == 0


async def test_the_report_limit_applies(migrated_database: str, worker: FakeWorker) -> None:
    fresh = {**HEADERS, "X-Install-Id": str(uuid.uuid4())}  # no counts from earlier tests
    async with make_client(migrated_database, worker, reports_per_install_day=1) as c:
        first, second = await record(c, fresh), await record(c, fresh)
        assert (await report(c, first, fresh)).status_code == 201
        limited = await report(c, second, fresh)
        assert (limited.status_code, limited.json()["error"]["code"]) == (429, "rate_limited")
