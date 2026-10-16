"""The worker's routes with a fake model runner: it returns, for any audio, what the lab's model
heard on a golden case, so the whole path (auth, body, decode, pipeline, result) runs without a
GPU."""

from __future__ import annotations

import json
import subprocess
from collections.abc import AsyncIterator
from typing import Any

import httpx
import numpy as np
import pytest

from app.engine.pipeline.heard import Heard
from app.worker.main import create_worker_app
from app.worker.service import WorkerService
from tests.unit.engine.test_pipeline_golden import GOLDEN, heard_for, without_new_fields

TOKEN = {"Authorization": "Bearer mojawid-dev-worker-token"}
GOLDEN_112 = json.loads((GOLDEN / "112001_manual.json").read_text())


class FakeRunner:
    """What the model heard on Husary 112:1 (from the lab's golden), whatever the audio."""

    device = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def heard(self, wave: np.ndarray) -> tuple[Heard, int]:
        self.calls += 1
        return heard_for(GOLDEN_112), 1


def _audio(seconds: float = 2.0) -> bytes:
    src = ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    return subprocess.run(
        ["ffmpeg", "-loglevel", "error", *src, "-f", "mp3", "pipe:1"],
        check=True,
        capture_output=True,
    ).stdout


@pytest.fixture
async def client() -> AsyncIterator[tuple[httpx.AsyncClient, FakeRunner]]:
    runner = FakeRunner()
    app = create_worker_app(lambda settings: runner)
    app.state.service = WorkerService(runner)  # the lifespan doesn't run under ASGITransport
    app.state.device = runner.device
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://worker") as c:
        yield c, runner


MANUAL_112: dict[str, str | int] = {"mode": "manual", "sura": 112, "aya_start": 1, "aya_end": 1}


async def _analyze(
    c: httpx.AsyncClient, params: dict[str, Any], body: bytes, **headers: str
) -> httpx.Response:
    return await c.post("/v1/analyze", params=params, content=body, headers={**TOKEN, **headers})


async def test_analyze_gives_the_labs_result(client: tuple[httpx.AsyncClient, FakeRunner]) -> None:
    c, runner = client
    r = await _analyze(c, MANUAL_112, _audio())
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["text"] == {"sura": 112, "aya_start": 1, "aya_end": 1, "prefixes": []}
    assert result["summary"]["exact_match"] == GOLDEN_112["report"]["exact_match"]
    ours = without_new_fields(result["report"])
    theirs = dict(GOLDEN_112["report"])
    theirs.pop("sifat_unreliable_probs")
    assert ours == theirs
    assert result["word_times"]
    assert result["engine"]["model_revision"] == "01a1ef9fbe40d144ef845101e89ff924aed3fef5"
    assert runner.calls == 1


async def test_token_required(client: tuple[httpx.AsyncClient, FakeRunner]) -> None:
    c, runner = client
    r = await c.post("/v1/analyze", params=MANUAL_112, content=_audio())
    assert (r.status_code, r.json()["error"]["code"]) == (401, "invalid_worker_token")
    r = await c.post("/v1/warm", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
    assert runner.calls == 0


@pytest.mark.parametrize(
    ("params", "body", "status", "code"),
    [
        (
            {**MANUAL_112, "reading": json.dumps({"madd_monfasel_len": 2})},
            None,
            400,
            "invalid_reading_settings",
        ),
        ({"mode": "manual", "sura": 1, "aya_start": 8}, None, 400, "invalid_text_selection"),
        ({"mode": "manual"}, None, 400, "invalid_text_selection"),
        ({**MANUAL_112, "reading": "not json"}, None, 422, "invalid_request"),
        (MANUAL_112, b"not audio" * 50, 422, "audio_unreadable"),
    ],
)
async def test_bad_requests_never_reach_the_model(
    client: tuple[httpx.AsyncClient, FakeRunner],
    params: dict[str, Any],
    body: bytes | None,
    status: int,
    code: str,
) -> None:
    c, runner = client
    r = await _analyze(c, params, body if body is not None else _audio())
    assert (r.status_code, r.json()["error"]["code"]) == (status, code)
    assert runner.calls == 0
    assert "not audio" not in r.text  # nothing of the upload comes back


async def test_too_large_upload(client: tuple[httpx.AsyncClient, FakeRunner]) -> None:
    c, runner = client
    r = await _analyze(c, MANUAL_112, b"\0" * (2 * 1024 * 1024 + 1))
    assert (r.status_code, r.json()["error"]["code"]) == (413, "audio_too_large")
    assert runner.calls == 0


async def test_auto_mode(client: tuple[httpx.AsyncClient, FakeRunner]) -> None:
    c, _ = client
    r = await _analyze(c, {"mode": "auto"}, _audio())
    assert r.status_code == 200, r.text
    assert r.json()["text"]["sura"] == 112
    assert r.json()["detection"] is not None


async def test_health_and_warm(client: tuple[httpx.AsyncClient, FakeRunner]) -> None:
    c, _ = client
    assert (await c.get("/healthz")).json() == {"ready": True, "device": "fake"}
    r = await c.post("/v1/warm", headers=TOKEN)
    assert r.json()["ready"] is True
