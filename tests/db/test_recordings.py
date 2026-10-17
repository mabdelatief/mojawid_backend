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

from app.db.session import dispose_engine
from app.errors import AppError
from tests.db.test_analyses import AUDIO, HEADERS, FakeWorker, make_client, post

PASSWORD = "a long enough password"
ADMIN = {"Authorization": "Basic " + base64.b64encode(f"admin:{PASSWORD}".encode()).decode()}
OTHER = {**HEADERS, "X-Install-Id": "7c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f"}
EMAIL = "m.tester@example.com"
DIR = Path(os.environ["MOJAWID_RECORDINGS_DIR"])


@pytest.fixture
async def worker() -> FakeWorker:
    return FakeWorker()


@pytest.fixture
async def client(
    migrated_database: str, engine: AsyncEngine, worker: FakeWorker
) -> AsyncIterator[httpx.AsyncClient]:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE analysis, rate_limit_counter, recording"))
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
