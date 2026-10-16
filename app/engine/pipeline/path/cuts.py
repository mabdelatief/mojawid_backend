"""The places a new piece of the recitation may start: every silence between heard letter groups.

Ported from tajweed_ai `muaalem_lab/path.py` (_split_points).
"""

from app.engine.pipeline.ctc import FRAME_SECONDS
from app.engine.pipeline.pauses import MIN_PAUSE_S, Pauses

SOFT_PAUSE_S = 0.15

Cut = tuple[int, str, tuple[float, float] | None]  # (group index, kind, the silence)


def split_points(group_frames: list[tuple[int, int]], pauses: Pauses) -> list[Cut]:
    """(group index where a new piece starts, "hard" | "soft", the silence) for every silence
    between heard letter groups."""

    def at(t: float) -> int:
        f = t / FRAME_SECONDS
        return sum(1 for a, _ in group_frames if a < f)

    out: dict[int, tuple[str, tuple[float, float]]] = {}
    for a, b in zip(pauses.speech, pauses.speech[1:], strict=False):
        k = at((a[1] + b[0]) / 2)
        if 0 < k < len(group_frames):
            out[k] = ("hard", (a[1], b[0]))
    raw = pauses.raw
    for a, b in zip(raw, raw[1:], strict=False):
        gap = b[0] - a[1]
        if SOFT_PAUSE_S <= gap < MIN_PAUSE_S:
            k = at((a[1] + b[0]) / 2)
            if 0 < k < len(group_frames) and k not in out:
                out[k] = ("soft", (a[1], b[0]))
    return sorted((k, kind, gap) for k, (kind, gap) in out.items())
