"""The inferred path, and its boundaries between segments.

Ported from tajweed_ai `muaalem_lab/path.py` (Boundary, Inferred, and the boundary-building tail
of `infer`).
"""

import dataclasses
from typing import Any

from app.engine.pipeline.path.cuts import Cut
from app.engine.text.structure import Structure, Word


@dataclasses.dataclass(frozen=True)
class Boundary:
    after_word: int  # index into the selected words
    resume_word: int | None  # where the next segment starts (None: joined)
    kind: str  # "stop" | "stop_back" | "joined" | "uncertain_stop" | "uncertain_joined"
    pause: tuple[float, float] | None


@dataclasses.dataclass
class Inferred:
    structure: Structure
    boundaries: list[Boundary]
    distance: int  # edit distance of what was heard to the inferred reference
    default_distance: int  # the same against the default structure (stops at ayah ends only)
    # not the default path (a stop inside an ayah, going back, joined ayat, or an undecided place)
    differs: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "structure": self.structure.to_json(),
            "distance": self.distance,
            "default_distance": self.default_distance,
            "differs": self.differs,
            "boundaries": [dataclasses.asdict(b) for b in self.boundaries],
        }


def boundaries(
    segs: list[tuple[int, int]], used_cuts: list[int], cuts: list[Cut], words: list[Word]
) -> list[Boundary]:
    """Stops between segments, and the ayah ends crossed without one. An ayah end inside a
    stretch that holds a short silence not taken as a stop may have been a stop after all."""
    out = []
    for k, ((_, b), (a2, _)) in enumerate(zip(segs, segs[1:], strict=False)):
        cut = cuts[used_cuts[k + 1]]
        kind = "uncertain_stop" if cut[1] == "soft" else "stop" if a2 == b + 1 else "stop_back"
        out.append(Boundary(b, a2, kind, cut[2]))
    seg_cut = [*used_cuts, len(cuts) - 1]
    unused_soft = [k for k, c in enumerate(cuts) if c[1] == "soft" and k not in used_cuts]
    for n, (a, b) in enumerate(segs):
        soft_inside = any(seg_cut[n] < k < seg_cut[n + 1] for k in unused_soft)
        for g in range(a, b):
            if words[g].ayah_last:
                kind = "uncertain_joined" if soft_inside else "joined"
                out.append(Boundary(g, None, kind, None))
    out.sort(key=lambda x: x.after_word)
    return out
