"""Write docs/rules-review/content.json: everything the teachers review, generated from the
rules table, the analysis' behaviour and a scan of the Quran with the phonetizer. Takes about
half a minute.

    .venv/bin/python -m tools.rules_review.build
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from typing import Any

from app.engine.text import tajweed
from app.engine.text.qt import alph
from app.engine.text.quran_text import ayah_words, surah_list
from app.engine.text.readable import ar_num
from app.model_pins import MUAALEM
from tools.rules_review import sections as S
from tools.rules_review import wording as W
from tools.rules_review.quran import example, load_ayah
from tools.rules_review.scan import scan, spread

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "rules-review" / "content.json"
COLOUR_EXAMPLES = 3


def _count_fact(n: int) -> tuple[str, str]:
    return (W.FACT_COUNT, ar_num(n))


def colours_section(found: S.Found) -> dict[str, Any]:
    items = []
    for cls in tajweed.CLASSES:
        title, body, kind = W.COLOURS[cls]
        it = S.item(
            f"colour.{cls}",
            title,
            "app",
            f"tajweed.py: {cls}",
            body=[body],
            examples=S.hit_examples(found, (kind,), COLOUR_EXAMPLES),
        )
        it["colour"] = cls
        items.append(it)
    return S.section("colours", items)


def engine_section(found: S.Found) -> dict[str, Any]:
    items = []
    for kind in W.ENGINE_ORDER:
        hits = found.get(kind, [])
        if not hits:
            continue
        title, body = W.ENGINE[kind]
        n = W.EXAMPLES_PER_KIND.get(kind, 5)
        items.append(
            S.item(
                f"engine.{kind}",
                title,
                "engine",
                f"scan.py: {kind}",
                body=[body],
                facts=[_count_fact(len(hits))],
                examples=[
                    example(load_ayah(h.sura, h.aya), h.start, h.end) for h in spread(hits, n)
                ],
            )
        )
    return S.section("engine", items)


def special_words_section() -> dict[str, Any]:
    items = []
    for k, case in enumerate(c for c in alph.uthmani.special_patterns if c.attr_name is None):
        examples = _find(case.pattern)
        items.append(
            S.item(
                f"special_word.{k}",
                f"«{examples[0]['text'][examples[0]['mark'][0] : examples[0]['mark'][1]]}»"
                if examples
                else case.pattern,
                "engine",
                "quran-transcript: special_patterns",
                body=[W.SPECIAL_WORD],
                facts=[_count_fact(len(examples))],
                examples=examples,
            )
        )
    return S.section("special_words", items)


def notes_section() -> dict[str, Any]:
    title, body = W.GENERAL_NOTE
    it = S.item("general.notes", title, "app", "", body=[body])
    it["kind"] = "note"
    return S.section("notes", [it])


def _find(pattern: str) -> list[dict[str, Any]]:
    out = []
    for s in surah_list():
        for a in range(1, s.ayat + 1):
            text = " ".join(ayah_words(s.index, a))
            for m in re.finditer(pattern, text):
                out.append(example(load_ayah(s.index, a), m.start(), m.end()))
    return out


def _hash(it: dict[str, Any]) -> str:
    keep = {k: it[k] for k in ("title", "body", "facts", "examples")}
    return hashlib.sha256(
        json.dumps(keep, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:16]


def build() -> dict[str, Any]:
    found = scan()
    sections = [
        S.settings_section(found),
        S.combos_section(),
        S.both_valid_section(found),
        S.practices_section(),
        S.judging_section(),
        colours_section(found),
        engine_section(found),
        special_words_section(),
        notes_section(),
    ]
    for sec in sections:
        for it in sec["items"]:
            it["hash"] = _hash(it)
    return {
        "title": "مراجعة أحكام التلاوة في مُجَوِّد",
        "riwaya": "حفص عن عاصم من طريق الشاطبية",
        "intro": W.INTRO,
        "status_labels": W.STATUS,
        "engine": {"model": MUAALEM.repo_id, "revision": MUAALEM.revision},
        "sections": sections,
    }


def main() -> None:
    content = build()
    ids = [it["id"] for sec in content["sections"] for it in sec["items"]]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate item ids")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(content, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(REPO)}: {len(ids)} items")


if __name__ == "__main__":
    main()
