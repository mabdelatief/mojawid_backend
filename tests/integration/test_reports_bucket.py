"""The real private reports bucket (Linode), with the key from .env: put, a signed link that
plays it, no anonymous access, delete. Run on demand:

    .venv/bin/pytest -m bucket tests/integration -q
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from app.adapters.object_store import S3ObjectStore
from app.config import Settings

pytestmark = pytest.mark.bucket


async def test_put_play_delete() -> None:
    settings = Settings()
    if not settings.reports_configured:
        pytest.skip("reports bucket not configured (.env)")
    store = S3ObjectStore(settings)
    key = f"reports/test-{uuid.uuid4()}"
    data = b"not really audio " * 64
    host = settings.reports_endpoint.replace("https://", f"https://{settings.reports_bucket}.")
    await store.put(key, data, "audio/mp4")
    async with httpx.AsyncClient(timeout=20) as http:
        try:
            url = await store.signed_url(key, 60)
            played = await http.get(url)
            assert played.content == data and played.headers["content-type"] == "audio/mp4"
            assert (await http.get(f"{host}/{key}")).status_code == 403  # private
        finally:
            await store.delete(key)
        assert (await http.get(url)).status_code in (403, 404)  # gone
