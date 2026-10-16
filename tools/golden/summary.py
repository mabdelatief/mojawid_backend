"""One reference, summarised the same way on both sides of the golden comparison: in tajweed_ai
(muaalem_lab) when the goldens are made, and in this repo (app.engine) when they're checked.

Duck-typed on purpose: it reads the attributes both Reference classes share, and imports nothing
from either project. The per-letter sifat and the character mappings are large, so they're kept
as hashes; everything else is kept verbatim so a difference shows up readably.
"""

import hashlib
import json
from typing import Any


def sha256_of(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def _segment(seg: Any) -> dict[str, Any]:
    return {
        "kind": seg.kind,
        "start": seg.start,
        "end": seg.end,
        "uthmani": seg.uthmani,
        "moshaf_overrides": dict(seg.moshaf_overrides),
        "words": [[w.sura, w.aya, w.word, w.start, w.end, w.ayah_last] for w in seg.words],
    }


def _mapping(m: Any) -> list[Any]:
    rules = [type(r).__name__ for r in (m.tajweed_rules or [])]
    return [list(m.pos), bool(m.deleted), rules]


def summarize(ref: Any, spans: list[list[Any]]) -> dict[str, Any]:
    """The comparable form of a reference and its tajweed spans."""
    phonetic = ref.phonetic
    return {
        "uthmani": ref.uthmani,
        "phonemes": phonetic.phonemes,
        "segments": [_segment(s) for s in ref.segments],
        "tajweed": [list(s) for s in spans],
        "sifat_sha256": sha256_of([s.model_dump() for s in phonetic.sifat]),
        "mappings_sha256": sha256_of([_mapping(m) for m in phonetic.mappings]),
    }
