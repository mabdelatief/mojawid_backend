"""The app skeleton: liveness, the error envelope, request ids, and validation errors that never
echo what was submitted. No database needed."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from app.errors import AppError
from app.main import create_app


class Item(BaseModel):
    """A body with one constrained field."""

    count: int


def _app_with_probe_routes() -> FastAPI:
    app = create_app()

    @app.get("/probe/app-error", response_model=Item)
    async def app_error() -> Item:
        raise AppError("too_many_ayat", "At most 6 ayat.", status_code=400)

    @app.get("/probe/crash", response_model=Item)
    async def crash() -> Item:
        raise RuntimeError("secret detail that must not leak")

    @app.post("/probe/items", status_code=201, response_model=Item)
    async def make_item(item: Item) -> Item:
        return item

    return app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=_app_with_probe_routes(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_healthz(client: httpx.AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_request_id_is_echoed_and_reused_when_well_formed(client: httpx.AsyncClient) -> None:
    assert len((await client.get("/healthz")).headers["x-request-id"]) == 32
    given = "abcdef12-3456"
    r = await client.get("/healthz", headers={"X-Request-ID": given})
    assert r.headers["x-request-id"] == given


async def test_malformed_request_id_is_replaced(client: httpx.AsyncClient) -> None:
    bad = "x\nfake log line"
    r = await client.get("/healthz", headers={"X-Request-ID": bad})
    assert r.headers["x-request-id"] != bad


async def test_app_error_envelope(client: httpx.AsyncClient) -> None:
    r = await client.get("/probe/app-error")
    assert r.status_code == 400
    error = r.json()["error"]
    assert error["code"] == "too_many_ayat"
    assert error["request_id"] == r.headers["x-request-id"]


async def test_unexpected_error_hides_internals(client: httpx.AsyncClient) -> None:
    r = await client.get("/probe/crash")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "secret" not in r.text


async def test_validation_error_never_echoes_input(client: httpx.AsyncClient) -> None:
    r = await client.post("/probe/items", json={"count": "SUBMITTED-VALUE"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"
    assert "SUBMITTED-VALUE" not in r.text


async def test_unknown_route_uses_the_envelope(client: httpx.AsyncClient) -> None:
    r = await client.get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
