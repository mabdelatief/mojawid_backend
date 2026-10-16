"""GET /v1/meta and POST /v1/reference (no database involved)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from app.main import create_app
from app.services.text_service import warm_up

HEADERS = {"X-Api-Key": "mojawid-dev-key", "X-Install-Id": "0b8a3f2e-2c1d-4e5f-9a7b-1c2d3e4f5a6b"}


@pytest.fixture(scope="module")
async def client() -> AsyncIterator[httpx.AsyncClient]:
    warm_up()
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _reference(client: httpx.AsyncClient, **body: Any) -> httpx.Response:
    return await client.post("/v1/reference", headers=HEADERS, json=body)


async def test_meta(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/meta", headers=HEADERS)
    assert r.status_code == 200
    meta = r.json()
    assert len(meta["surahs"]) == 114
    assert meta["surahs"][1] == {"index": 2, "name": meta["surahs"][1]["name"], "ayat": 286}
    settings = {s["name"]: s for s in meta["reading"]}
    assert [c["value"] for c in settings["madd_monfasel_len"]["choices"]] == [4, 5]
    assert settings["madd_monfasel_len"]["choices"][0]["label_ar"] == "٤ حركات"
    assert {c["label_ar"] for c in settings["meem_mokhfah"]["choices"]} == {"ميم", "إخفاء"}
    assert "alif_salasila" not in settings  # fixed by the teachers' rulings, not offered
    assert meta["practices"] == {"raum": False}
    assert meta["limits"]["max_ayat_manual"] == 6
    assert meta["engine"]["quran_transcript"] == "0.6.4+muaalem.2"


async def test_reference_for_fatiha_with_openings(client: httpx.AsyncClient) -> None:
    r = await _reference(client, sura=1, aya_start=1, aya_end=3, prefixes=["istiaatha", "basmala"])
    assert r.status_code == 200
    ref = r.json()
    # in al-Fatiha the basmala is ayah 1 itself, so only the isti'adha is added
    assert [s["kind"] for s in ref["segments"]] == [
        "istiaatha",
        "recitation",
        "recitation",
        "recitation",
    ]
    words = [w for s in ref["segments"] for w in s["words"]]
    assert [(w["aya"], w["word"]) for w in words[:4]] == [(1, 0), (1, 1), (1, 2), (1, 3)]
    for w in words:
        assert " " not in ref["uthmani"][w["start"] : w["end"]]
    assert ref["tajweed"]
    assert set(ref["classes_present"]) <= {span[2] for span in ref["tajweed"]}


async def test_reading_settings_change_where_the_text_splits(client: httpx.AsyncClient) -> None:
    # 75:27 «مَنْ رَاقٍ»: connected with sakt by default; set to a stop, it splits in two
    sakt = (await _reference(client, sura=75, aya_start=27, aya_end=27)).json()
    stop = (
        await _reference(
            client, sura=75, aya_start=27, aya_end=27, reading={"sakt_man_raq": "waqf"}
        )
    ).json()
    assert len(sakt["segments"]) == 1
    assert len(stop["segments"]) == 2
    assert sakt["uthmani"].replace(" ", "") == stop["uthmani"].replace(" ", "")


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"sura": 1, "aya_start": 1, "aya_end": 7}, 400, "too_many_ayat"),
        ({"sura": 1, "aya_start": 7, "aya_end": 8}, 400, "invalid_text_selection"),
        ({"sura": 2, "aya_start": 5, "aya_end": 4}, 400, "invalid_text_selection"),
        ({"sura": 2, "aya_start": 4, "aya_end": 4, "reading": {"madd_monfasel_len": 2}}, 400,
         "invalid_reading_settings"),
        ({"sura": 2, "aya_start": 4, "aya_end": 4, "reading": {"sakt_man_raq": "idraj"}}, 400,
         "invalid_reading_settings"),
        ({"sura": 2, "aya_start": 4, "aya_end": 4, "prefixes": ["x"]}, 422, "invalid_request"),
        ({"sura": 115, "aya_start": 1, "aya_end": 1}, 422, "invalid_request"),
    ],
)  # fmt: skip
async def test_reference_errors(
    client: httpx.AsyncClient, body: dict[str, Any], status: int, code: str
) -> None:
    r = await client.post("/v1/reference", headers=HEADERS, json=body)
    assert (r.status_code, r.json()["error"]["code"]) == (status, code)


async def test_six_ayat_are_fast_once_warm(client: httpx.AsyncClient) -> None:
    body = {"sura": 2, "aya_start": 1, "aya_end": 6}
    await _reference(client, **body)  # warm the phonetizer cache for these ayat
    started = time.perf_counter()
    r = await _reference(client, **body)
    assert r.status_code == 200
    assert time.perf_counter() - started < 0.05


async def test_key_required(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/meta")
    assert r.json()["error"]["code"] == "invalid_api_key"
