"""Where a position of the reference's Uthmani text is: its segment, and the word in it."""

from app.engine.text.reference import Reference, SegmentWord


def word_at(ref: Reference, pos: int) -> tuple[int, int | None, SegmentWord | None]:
    """(segment index, index of the word in the segment, the word). The space after a word
    counts as that word's (as the lab's letter groups place it). Openings have no words."""
    seg_i = ref.segment_at(pos)
    words = ref.segments[seg_i].words
    k = next((k for k, w in enumerate(words) if w.start <= pos < w.end + 1), None)
    return seg_i, k, words[k] if k is not None else None
