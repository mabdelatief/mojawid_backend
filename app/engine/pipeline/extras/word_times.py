"""Each recited word's time span in the user's own recording, for «استمع لتسجيلي».

From what was heard to the words: each heard letter group has its frames (40 ms each, from the
decoder). The phonetic diff maps heard characters to reference characters (one to one inside
equal blocks; a changed block maps its heard span to its reference span), and the reference maps
its characters to the Uthmani text, so to a segment and a word. A word's span runs from its first
heard group's first frame to its last group's last frame, padded by PAD_S without reaching into
the neighbouring words. Each segment is one recital of its words, so a word said again after going
back gets its own entry; a skipped word, or an opening, has none.
"""

from typing import Any

from app.engine.pipeline.ctc import FRAME_SECONDS
from app.engine.pipeline.extras.places import word_at
from app.engine.pipeline.heard import Heard
from app.engine.text.qt import chunck_phonemes, extract_ref_phonetic_to_uthmani
from app.engine.text.reference import Reference

PAD_S = 0.1


def _heard_to_ref(diff: list[dict[str, Any]], n_heard: int) -> list[list[int]]:
    """Per heard character, the reference characters it stands for."""
    out: list[list[int]] = [[] for _ in range(n_heard)]
    for blk in diff:
        (i1, i2), (j1, j2) = blk["ref_span"], blk["pred_span"]
        if blk["op"] == "equal":
            for k in range(j2 - j1):
                out[j1 + k].append(i1 + k)
        else:
            for j in range(j1, j2):
                out[j].extend(range(i1, i2))
    return out


def _word_frames(
    heard: Heard, ref: Reference, diff: list[dict[str, Any]]
) -> dict[tuple[int, int], list[int]]:
    """(segment, word in segment) -> [first frame, last frame] of the heard groups in it."""
    to_ref = _heard_to_ref(diff, len(heard.text))
    ph_to_uth = extract_ref_phonetic_to_uthmani(ref.phonetic.mappings)
    spans: dict[tuple[int, int], list[int]] = {}
    pos = 0
    groups = chunck_phonemes(heard.text) if heard.text else []
    for g, (f0, f1) in zip(groups, heard.group_frames, strict=True):
        ref_chars = {i for j in range(pos, pos + len(g)) for i in to_ref[j]}
        pos += len(g)
        for seg_i, k in {word_at(ref, ph_to_uth[i])[:2] for i in ref_chars if i < len(ph_to_uth)}:
            if k is None:
                continue
            span = spans.setdefault((seg_i, k), [f0, f1])
            span[0], span[1] = min(span[0], f0), max(span[1], f1)
    return spans


def word_times(
    heard: Heard, ref: Reference, diff: list[dict[str, Any]], duration_s: float
) -> list[dict[str, Any]]:
    """[{segment, word, sura, aya, start_s, end_s}] in time order."""
    raw = sorted(
        (
            (f0 * FRAME_SECONDS, f1 * FRAME_SECONDS, seg_i, k)
            for (seg_i, k), (f0, f1) in _word_frames(heard, ref, diff).items()
        ),
    )
    out = []
    for n, (start, end, seg_i, k) in enumerate(raw):
        lo = raw[n - 1][1] if n else 0.0
        hi = raw[n + 1][0] if n + 1 < len(raw) else duration_s
        w = ref.segments[seg_i].words[k]
        out.append(
            {
                "segment": seg_i,
                "word": w.word,
                "sura": w.sura,
                "aya": w.aya,
                "start_s": round(max(start - PAD_S, min(lo, start), 0.0), 3),
                "end_s": round(min(end + PAD_S, max(hi, end), duration_s), 3),
            }
        )
    return out
