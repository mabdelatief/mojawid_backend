"""The teachers' review (tools/rules_review): the generated content covers every rules entry and
quotes the Quran exactly, and the server saves each teacher's answers under her login."""

from __future__ import annotations

import json
import pathlib
import sqlite3
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from app.engine.text import rules as R
from app.engine.text.moshaf import moshaf_all_options
from app.engine.text.quran_text import ayah_words
from app.engine.text.tajweed import CLASSES
from tools.rules_review import build, export, server, store

CONTENT: dict[str, Any] = json.loads(server.CONTENT.read_text())
ITEMS = {it["id"]: it for sec in CONTENT["sections"] for it in sec["items"]}
EMAIL = {"cf-access-authenticated-user-email": "Teacher@Example.com"}


def test_ids_are_unique_and_hashes_match_the_text() -> None:
    ids = [it["id"] for sec in CONTENT["sections"] for it in sec["items"]]
    assert len(ids) == len(set(ids))
    for it in ITEMS.values():
        assert it["hash"] == build._hash(it), it["id"]


def test_every_rules_entry_has_an_item() -> None:
    settings = {o.name for o in moshaf_all_options()} | set(R.DEFAULT.fixed)
    assert {f"setting.{n}" for n in settings} <= ITEMS.keys()
    allowed = {f"setting.{n}" for n in R.DEFAULT.allowed if n != "rewaya"}
    assert all(ITEMS[i]["status"] == "ruled" for i in allowed)
    assert all(ITEMS[f"setting.{n}"]["status"] == "fixed" for n in R.DEFAULT.fixed)
    assert all(ITEMS[f"setting.{n}"]["status"] == "unreviewed" for n in R.UNREVIEWED)
    assert {f"madd_lengths.{k}" for k in R.DEFAULT.madd_lengths} <= ITEMS.keys()
    both = next(s for s in CONTENT["sections"] if s["id"] == "both_valid")
    assert len(both["items"]) == len(R.DEFAULT.both_valid)
    assert "practice.raum" in ITEMS
    assert {f"colour.{c}" for c in CLASSES} <= ITEMS.keys()


def test_examples_quote_the_quran_exactly() -> None:
    examples = [ex for it in ITEMS.values() for ex in it["examples"]]
    assert len(examples) > 250
    for ex in examples:
        ayah = " ".join(ayah_words(ex["sura"], ex["aya"]))
        assert ex["text"] in ayah, ex["ref"]
        if ex["mark"]:
            a, b = ex["mark"]
            assert 0 <= a < b <= len(ex["text"])
        for s, e, cls in ex["spans"]:
            assert 0 <= s < e <= len(ex["text"]) and cls in CLASSES


def test_stop_rulings_are_shown_read_with_the_stop() -> None:
    misr = ITEMS["both_valid.10.87.7"]["examples"][0]
    assert misr["at_stop"] and misr["cut_after"]
    assert "الراء مفخمة" in misr["notes"]
    qitr = ITEMS["both_valid.34.12.9"]["examples"][0]
    assert qitr["at_stop"] and "الراء مرققة" in qitr["notes"]
    assert all(ex["at_stop"] for ex in ITEMS["setting.alif_salasila"]["examples"])


def test_leen_madd_is_shown_as_a_madd_not_a_ghunnah() -> None:
    for ex in ITEMS["engine.madd_leen"]["examples"]:
        assert "مد ٤ حركات" in ex["expect"] and "غنة" not in ex["expect"], ex["ref"]


@pytest.mark.slow
def test_committed_content_is_what_the_builder_makes() -> None:
    assert json.loads(json.dumps(build.build(), ensure_ascii=False)) == CONTENT


# --- server --------------------------------------------------------------------------------


@pytest.fixture
async def client(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("MOJAWID_REVIEW_DB", str(tmp_path / "answers.sqlite3"))
    monkeypatch.delenv(server.DEV_EMAIL, raising=False)
    monkeypatch.setattr(server, "NAMES", tmp_path / "names.json")
    transport = httpx.ASGITransport(app=server.create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://review") as c:
        yield c


async def test_login_required(client: httpx.AsyncClient) -> None:
    for path in ("/mojawid/", "/mojawid/api/content", "/mojawid/api/answers", "/mojawid/api/me"):
        assert (await client.get(path)).status_code == 401, path
    r = await client.put(
        "/mojawid/api/answers/practice.raum", json={"verdict": "approve", "hash": "x"}
    )
    assert r.status_code == 401


async def test_page_content_and_me(client: httpx.AsyncClient) -> None:
    r = await client.get("/mojawid/", headers=EMAIL)
    assert r.status_code == 200 and 'dir="rtl"' in r.text
    assert r.headers["cache-control"] == "no-cache"
    assert (await client.get("/mojawid/static/app.js", headers=EMAIL)).status_code == 200
    content = (await client.get("/mojawid/api/content", headers=EMAIL)).json()
    assert content["sections"][0]["id"] == "settings"
    me = (await client.get("/mojawid/api/me", headers=EMAIL)).json()
    assert me == {"email": "teacher@example.com", "name": "teacher"}
    bare = await client.get("/mojawid")
    assert bare.status_code == 307 and bare.headers["location"] == "/mojawid/"


async def test_answers_round_trip(client: httpx.AsyncClient, tmp_path: pathlib.Path) -> None:
    item = ITEMS["setting.raa_misr"]
    url = "/mojawid/api/answers/setting.raa_misr"
    body = {"verdict": "correct", "correction": "  نص التصحيح  ", "hash": item["hash"]}
    r = await client.put(url, json=body, headers=EMAIL)
    assert r.status_code == 200
    assert r.json()["correction"] == "نص التصحيح"
    other = {"cf-access-authenticated-user-email": "sister@example.com"}
    await client.put(url, json={"verdict": "approve", "hash": "old"}, headers=other)
    rows = (await client.get("/mojawid/api/answers", headers=EMAIL)).json()
    got = {r["reviewer"]: (r["verdict"], r["item_hash"] == item["hash"]) for r in rows}
    assert got == {
        "teacher@example.com": ("correct", True),
        "sister@example.com": ("approve", False),
    }
    assert (await client.delete(url, headers=EMAIL)).status_code == 204
    rows = (await client.get("/mojawid/api/answers", headers=EMAIL)).json()
    assert [r["reviewer"] for r in rows] == ["sister@example.com"]
    log = sqlite3.connect(tmp_path / "answers.sqlite3").execute("SELECT count(*) FROM answers_log")
    assert log.fetchone()[0] == 3  # every change is kept


async def test_bad_answers_are_refused(client: httpx.AsyncClient) -> None:
    put = client.put
    r = await put(
        "/mojawid/api/answers/nope", json={"verdict": "approve", "hash": "x"}, headers=EMAIL
    )
    assert r.status_code == 404
    r = await put(
        "/mojawid/api/answers/practice.raum", json={"verdict": "maybe", "hash": "x"}, headers=EMAIL
    )
    assert r.status_code == 422


def test_export_lists_every_item_with_its_answers(tmp_path: pathlib.Path) -> None:
    db = tmp_path / "a.sqlite3"
    store.save("practice.raum", "t@example.com", "correct", "سطر أول\nسطر ثانٍ", "old", db)
    md = export.render(CONTENT, store.all_answers(db))
    assert md.count("### ") == len(ITEMS)
    assert "**t**: يحتاج تصحيحًا (أُجيب عن نص أقدم)" in md
    assert "  > سطر ثانٍ" in md
    assert "بنود أُجيب عنها: 1 من" in md
