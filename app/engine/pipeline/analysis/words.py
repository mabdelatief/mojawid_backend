"""Positions in the Uthmani text: letter clusters, word indexes, and the marked words.

Ported from tajweed_ai `muaalem_lab/analysis.py` (_is_mark, _cluster_span, _word_index,
_uthmani_segments).
"""

import unicodedata
from typing import Any

Row = dict[str, Any]


def _is_mark(ch: str) -> bool:
    return unicodedata.category(ch) in ("Mn", "Me") or ch == "ـ"  # marks and tatweel


def cluster_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Widen [start, end) so it never splits a letter from its marks. Zero-width spans
    (insertions) stay zero-width."""
    if start == end:
        return start, end
    while start > 0 and start < len(text) and _is_mark(text[start]):
        start -= 1
    while end < len(text) and _is_mark(text[end]):
        end += 1
    return start, end


def word_index(text: str, pos: int) -> int:
    """The word (counted over the whole Uthmani string) a position falls in."""
    return text.count(" ", 0, pos)


def _runs(text: str, start: int, end: int, cover: list[set[int]]) -> list[Row]:
    runs, k = [], start
    while k < end:
        j = k
        while j < end and cover[j] == cover[k]:
            j += 1
        runs.append({"text": text[k:j], "errors": sorted(cover[k])})
        k = j
    return runs


def uthmani_segments(text: str, rows: list[Row]) -> list[Row]:
    """Split the text into words, and each word into runs of characters that share the same set
    of errors. Insertions (zero width) mark the whole word."""
    cover: list[set[int]] = [set() for _ in text]
    word_errors: dict[int, set[int]] = {}
    for r in rows:
        s, t = r["uthmani_span"]
        word_errors.setdefault(r["word_index"], set()).add(r["id"])
        for k in range(s, t):
            cover[k].add(r["id"])
    words, start = [], 0
    for w_idx, word in enumerate(text.split(" ")):
        words.append(
            {"index": w_idx, "start": start, "runs": _runs(text, start, start + len(word), cover),
             "errors": sorted(word_errors.get(w_idx, ()))}
        )  # fmt: skip
        start += len(word) + 1
    return words
