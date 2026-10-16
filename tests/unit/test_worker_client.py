"""The API's worker client against a fake worker (httpx MockTransport) and a fake clock: retries
while the worker starts, never after a read timeout, and the worker's errors passed through."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.adapters.worker_client import WorkerClient
from app.errors import AppError

TOKEN = "Bearer test-token"
Handler = Callable[[httpx.Request], httpx.Response]


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def client(handler: Handler, fake: FakeTime, window: float = 90.0) -> WorkerClient:
    http = httpx.AsyncClient(
        base_url="http://worker", headers={"Authorization": TOKEN},
        transport=httpx.MockTransport(handler),
    )  # fmt: skip
    return WorkerClient(http, window, sleep=fake.sleep, clock=fake.clock)


def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"text": {"sura": 1}})


async def test_sends_the_body_and_token_and_returns_the_result() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return ok(request)

    result = await client(handler, FakeTime()).analyze(b"AUDIO", {"mode": "manual", "sura": 1})
    assert result == {"text": {"sura": 1}}
    req = seen[0]
    assert req.url.path == "/v1/analyze" and req.content == b"AUDIO"
    assert req.headers["authorization"] == TOKEN
    assert dict(req.url.params) == {"mode": "manual", "sura": "1"}


async def test_connection_refused_then_ready_is_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("refused", request=request)
        if calls == 2:
            return httpx.Response(503)
        return ok(request)

    fake = FakeTime()
    assert await client(handler, fake).analyze(b"A", {}) == {"text": {"sura": 1}}
    assert calls == 3 and fake.slept == [0.5, 1.0]


async def test_gives_up_after_the_retry_window() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    fake = FakeTime()
    with pytest.raises(AppError) as err:
        await client(handler, fake, window=20.0).analyze(b"A", {})
    assert (err.value.code, err.value.status_code) == ("analysis_unavailable", 503)
    assert fake.now <= 20.0 and calls == len(fake.slept) + 1


async def test_a_read_timeout_is_never_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(AppError) as err:
        await client(handler, FakeTime()).analyze(b"A", {})
    assert (err.value.code, err.value.status_code) == ("analysis_timeout", 504)
    assert calls == 1


async def test_a_dropped_connection_after_sending_is_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.RemoteProtocolError("disconnected", request=request)

    with pytest.raises(AppError) as err:
        await client(handler, FakeTime()).analyze(b"A", {})
    assert err.value.code == "analysis_unavailable" and calls == 1


async def test_the_workers_own_errors_pass_through() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        error = {"code": "audio_unreadable", "message": "Could not read the recording."}
        return httpx.Response(422, json={"error": error})

    with pytest.raises(AppError) as err:
        await client(handler, FakeTime()).analyze(b"A", {})
    assert (err.value.code, err.value.status_code) == ("audio_unreadable", 422)


@pytest.mark.parametrize("status", [401, 500])
async def test_our_misconfiguration_or_a_crash_is_unavailable(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status, json={"error": {"code": "invalid_worker_token", "message": "x"}}
        )

    with pytest.raises(AppError) as err:
        await client(handler, FakeTime()).analyze(b"A", {})
    assert (err.value.code, err.value.status_code) == ("analysis_unavailable", 503)


async def test_warm() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/warm"
        return httpx.Response(200, json={"ready": True, "device": "cuda"})

    assert await client(handler, FakeTime()).warm() is True


async def test_warm_means_it_answered_recently() -> None:
    statuses = iter([401, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(statuses), json={"ready": True, "device": "cuda"})

    fake = FakeTime()
    worker = client(handler, fake)
    assert not worker.is_warm(240)
    assert await worker.warm() is False  # a 401 is our misconfiguration, not a live worker
    assert not worker.is_warm(240)
    assert await worker.warm() is True
    assert worker.is_warm(240)
    fake.now += 300
    assert not worker.is_warm(240)
