"""Extra fields on each error row, for the app.

- `sura`, `aya`, `word`: the place in the Quran (word: index within the ayah, as everywhere).
  An opening (isti'adha, basmala) has no ayah: sura and aya are None, word counts its words.
- `key`: `"{sura}:{aya}:{word}:{error_type}"` (openings: `"{kind}:0:{word}:{error_type}"`).
  Stable between attempts, so the app can compare them (fixed / remaining / new). It is not
  unique: the app compares sets.
- `mark`: what the app draws: `letter` / `haraka` / `tajweed` for a mistake, `uncertain`, or,
  when it isn't a mistake, `variant` (an allowed way) or `false_alarm`.
- `counted`: a real mistake. Never an uncertain place, never an allowed variant.
- `expected_harakat` / `heard_harakat`: madd rows only, in harakat. explain_error already counts
  a leen madd in harakat (N letters → N + 1), so these are its lengths unchanged. Never for
  ghunnah, whose script run isn't harakat.
"""

from typing import Any

from app.engine.pipeline.extras.places import word_at
from app.engine.text.groups import MADD_RULES
from app.engine.text.reference import Reference

MARK_OF = {"normal": "letter", "tashkeel": "haraka", "tajweed": "tajweed"}


def _place(ref: Reference, pos: int) -> tuple[int | None, int | None, int, str]:
    seg_i, k, w = word_at(ref, pos)
    seg = ref.segments[seg_i]
    if w is not None:
        return w.sura, w.aya, w.word, f"{w.sura}:{w.aya}:{w.word}"
    word = seg.uthmani.count(" ", 0, max(0, pos - seg.start)) if k is None else k
    return None, None, word, f"{seg.kind}:0:{word}"


def _mark(row: dict[str, Any]) -> str:
    if row["likely_false_alarm"]:
        return "variant" if row["valid_variant"] else "false_alarm"
    if row["uncertain"]:
        return "uncertain"
    return MARK_OF.get(row["error_type"], "tajweed")


def _harakat(row: dict[str, Any]) -> tuple[int | None, int | None]:
    names = {r["en"] for r in row["rules"]}
    if row["ghunnah"] or not names & MADD_RULES:
        return None, None
    # explain_error's lengths are already harakat, a leen madd included (3 letters → 4):
    # checked 2026-10-16. Nothing to add.
    return row["expected_len"], row["predicted_len"]


def add_row_fields(rows: list[dict[str, Any]], ref: Reference) -> None:
    """Add the fields above to every error row, in place."""
    for row in rows:
        sura, aya, word, where = _place(ref, row["uthmani_pos"][0])
        exp_h, heard_h = _harakat(row)
        mark = _mark(row)
        row.update(
            sura=sura,
            aya=aya,
            word=word,
            key=f"{where}:{row['error_type']}",
            mark=mark,
            counted=mark in ("letter", "haraka", "tajweed"),
            expected_harakat=exp_h,
            heard_harakat=heard_h,
        )
