"""Reports and the admin page against the test database, with an in-memory bucket: consent, the
upload rules, the admin login, «reviewed» deleting the recording, and the purge."""

from __future__ import annotations

import base64
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.api.deps import get_object_store
from app.config import Settings, get_settings
from app.db.session import dispose_engine, get_engine
from app.main import create_app
from app.services.maintenance_service import MaintenanceService

INSTALL = "0b8a3f2e-2c1d-4e5f-9a7b-1c2d3e4f5a6b"
HEADERS = {"X-Api-Key": "mojawid-dev-key", "X-Install-Id": INSTALL}
OTHER = {**HEADERS, "X-Install-Id": "7c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f"}
PASSWORD = "a long enough password"
ADMIN = {"Authorization": "Basic " + base64.b64encode(f"admin:{PASSWORD}".encode()).decode()}
AUDIO = b"fake-m4a-bytes" * 100
REVIEWED_TOKEN = (
    r'action="/admin/reports/[^"]+/reviewed">\s*<input type="hidden" name="csrf" '
    r'value="([0-9a-f]+)"'
)
RESULT: dict[str, Any] = {
    "text": {"sura": 112, "aya_start": 1, "aya_end": 1},
    "summary": {"mistakes": 1, "uncertain": 0, "exact_match": False},
    "report": {"errors": [{
        "counted": True, "sura": 112, "aya": 1, "word": 2, "mark": "tajweed", "ghunnah": None,
        "uthmani_text": "ٱللَّهُ", "expected_text": "لَّاهُ", "heard_text": "لَاهُ",
    }]},
}  # fmt: skip


@dataclass
class FakeStore:
    objects: dict[str, tuple[bytes, str]] = field(default_factory=dict)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    async def signed_url(self, key: str, seconds: int) -> str:
        return f"https://mojawid-reports.eu-central-1.linodeobjects.com/{key}?sig=x"


@pytest.fixture
async def store() -> FakeStore:
    return FakeStore()


def make_client(db: str, store: FakeStore | None, **over: Any) -> httpx.AsyncClient:
    over.setdefault("admin_password_hash", PasswordHasher().hash(PASSWORD))
    settings = Settings(database_url=db, **over)
    get_engine(settings)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_object_store] = lambda: store
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(
    migrated_database: str, engine: AsyncEngine, store: FakeStore
) -> AsyncIterator[httpx.AsyncClient]:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE report, rate_limit_counter"))
    await dispose_engine()
    async with make_client(migrated_database, store) as c:
        yield c
    await dispose_engine()


def body(**over: Any) -> dict[str, Any]:
    return {
        "consent": True, "category": "false_mistake", "word": {"sura": 112, "aya": 1, "word": 2},
        "note": "قرأتها صحيحة", "result": RESULT, "reading": {"madd_monfasel_len": 4},
        "app_version": "0.1.0", **over,
    }  # fmt: skip


async def create(c: httpx.AsyncClient, headers: dict[str, str] = HEADERS, **over: Any) -> str:
    r = await c.post("/v1/reports", json=body(**over), headers=headers)
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def upload(
    c: httpx.AsyncClient, rid: str, headers: dict[str, str] = HEADERS
) -> httpx.Response:
    h = {**headers, "Content-Type": "audio/mp4"}
    return await c.put(f"/v1/reports/{rid}/audio", content=AUDIO, headers=h)


async def test_report_flow_and_review(client: httpx.AsyncClient, store: FakeStore) -> None:
    rid = await create(client)
    assert (await upload(client, rid)).status_code == 204
    assert store.objects[f"reports/{rid}"] == (AUDIO, "audio/mp4")
    again = await upload(client, rid)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "report_audio_exists")

    listing = await client.get("/admin", headers=ADMIN)
    assert listing.status_code == 200 and rid in listing.text
    assert listing.headers["cache-control"] == "no-store"
    page = await client.get(f"/admin/reports/{rid}", headers=ADMIN)
    assert page.status_code == 200
    assert "قرأتها صحيحة" in page.text and "لَاهُ" in page.text and "?sig=x" in page.text
    token = re.search(REVIEWED_TOKEN, page.text)
    assert token

    bad = await client.post(f"/admin/reports/{rid}/reviewed", data={"csrf": "x"}, headers=ADMIN)
    assert (bad.status_code, bad.json()["error"]["code"]) == (403, "csrf_failed")
    done = await client.post(
        f"/admin/reports/{rid}/reviewed", data={"csrf": token.group(1)}, headers=ADMIN
    )
    assert done.status_code == 303
    assert store.objects == {}  # the recording is gone at review
    assert "Deleted at review" in (await client.get(f"/admin/reports/{rid}", headers=ADMIN)).text


async def test_delete_report(client: httpx.AsyncClient, store: FakeStore) -> None:
    rid = await create(client)
    await upload(client, rid)
    page = await client.get(f"/admin/reports/{rid}", headers=ADMIN)
    token = re.findall(r'name="csrf" value="([0-9a-f]+)"', page.text)[-1]
    r = await client.post(f"/admin/reports/{rid}/delete", data={"csrf": token}, headers=ADMIN)
    assert r.status_code == 303 and store.objects == {}
    assert (await client.get(f"/admin/reports/{rid}", headers=ADMIN)).status_code == 404


@pytest.mark.parametrize(
    ("over", "status", "code"),
    [
        ({"consent": False}, 400, "consent_required"),
        ({"category": "nonsense"}, 422, "invalid_request"),
        ({"note": "x" * 1001}, 422, "invalid_request"),
    ],
)
async def test_bad_reports(
    client: httpx.AsyncClient, over: dict[str, Any], status: int, code: str
) -> None:
    r = await client.post("/v1/reports", json=body(**over), headers=HEADERS)
    assert (r.status_code, r.json()["error"]["code"]) == (status, code)


async def test_upload_rules(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    rid = await create(client)
    other = await upload(client, rid, OTHER)
    assert (other.status_code, other.json()["error"]["code"]) == (404, "report_not_found")
    assert (await upload(client, str(uuid.uuid4()))).status_code == 404
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE report SET created_at = now() - interval '2 hours'"))
    late = await upload(client, rid)
    assert (late.status_code, late.json()["error"]["code"]) == (410, "report_upload_expired")
    too_big = await client.put(
        f"/v1/reports/{await create(client)}/audio", content=b"\0" * (2 * 1024 * 1024 + 1),
        headers=HEADERS,
    )  # fmt: skip
    assert (too_big.status_code, too_big.json()["error"]["code"]) == (413, "audio_too_large")
    no_key = await client.post("/v1/reports", json=body(), headers={"X-Install-Id": INSTALL})
    assert no_key.status_code == 401


async def test_admin_login(migrated_database: str, client: httpx.AsyncClient) -> None:
    r = await client.get("/admin")
    assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Basic")
    wrong = {"Authorization": "Basic " + base64.b64encode(b"admin:nope").decode()}
    assert (await client.get("/admin", headers=wrong)).status_code == 401
    await dispose_engine()
    async with make_client(migrated_database, None, admin_password_hash="") as off:
        assert (await off.get("/admin", headers=ADMIN)).status_code == 404


async def test_reports_off_without_a_bucket(
    migrated_database: str, client: httpx.AsyncClient
) -> None:
    await dispose_engine()
    async with make_client(migrated_database, None) as c:
        r = await c.post("/v1/reports", json=body(), headers=HEADERS)
    assert (r.status_code, r.json()["error"]["code"]) == (503, "reports_unavailable")


async def test_report_limit(
    migrated_database: str, client: httpx.AsyncClient, store: FakeStore
) -> None:
    await dispose_engine()
    async with make_client(migrated_database, store, reports_per_install_day=1) as c:
        await create(c)
        r = await c.post("/v1/reports", json=body(), headers=HEADERS)
    assert (r.status_code, r.json()["error"]["code"]) == (429, "rate_limited")


async def test_purge(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    never_sent, reviewed_long_ago, open_one = [await create(client) for _ in range(3)]
    for rid in (reviewed_long_ago, open_one):
        await upload(client, rid)
    now = datetime.now(UTC)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE report SET created_at = :t WHERE id = :i"),
            {"t": now - timedelta(hours=2), "i": uuid.UUID(never_sent)},
        )
        await conn.execute(
            text("UPDATE report SET reviewed_at = :t, audio_key = NULL WHERE id = :i"),
            {"t": now - timedelta(days=31), "i": uuid.UUID(reviewed_long_ago)},
        )
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as session:
        purged = await MaintenanceService(session, Settings()).purge(now)
    assert purged.reports == 2
    async with engine.begin() as conn:
        left = (await conn.execute(text("SELECT id::text FROM report"))).scalars().all()
    assert left == [open_one]  # an open report with its recording waits for review
