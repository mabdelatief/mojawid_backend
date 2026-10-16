"""The pipeline golden cases: Husary recordings (from our own bucket) analysed by tajweed_ai and
by the port. Each case's audio is a list of (ayah file, seconds of silence after it), so joined
ayat, an opening, and going back are built from single-ayah files. Imports nothing from either
project.
"""

import pathlib
import urllib.request
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[2]
AUDIO_DIR = REPO / ".cache" / "test_audio" / "Husary_64kbps"
GOLDEN_DIR = REPO / "tests" / "golden" / "pipeline"  # committed: the L1 check runs without a GPU
BUCKET = "https://verseaudiofiles.eu-central-1.linodeobjects.com/Husary_64kbps/"


def _case(
    cid: str, audio: list[tuple[str, float]], text: dict[str, Any] | None, **kw: Any
) -> dict[str, Any]:
    return {
        "id": cid,
        "audio": audio,
        "mode": "manual" if text is not None else "auto",
        "text": text,
        "reading": kw.get("reading", {}),
        "raum": kw.get("raum", False),
    }


def _text(
    sura: int, a: int, b: int | None = None, prefixes: tuple[str, ...] = ()
) -> dict[str, Any]:
    return {"sura": sura, "aya_start": a, "aya_end": b or a, "prefixes": list(prefixes)}


_SINGLE = [("001001", 1, 1), ("001002", 1, 2), ("001003", 1, 3), ("001007", 1, 7),
           ("067001", 67, 1), ("112001", 112, 1)]  # fmt: skip

CASES: list[dict[str, Any]] = [
    *(_case(f"{key}_manual", [(key, 0.0)], _text(s, a)) for key, s, a in _SINGLE),
    *(_case(f"{key}_auto", [(key, 0.0)], None) for key, _, _ in _SINGLE),
    _case("001007_manual_aared6", [("001007", 0.0)], _text(1, 7), reading={"madd_aared_len": 6}),
    _case("112001_manual_raum", [("112001", 0.0)], _text(112, 1), raum=True),
    _case("001002-3_joined_manual", [("001002", 0.0), ("001003", 0.0)], _text(1, 2, 3)),
    _case("001002-3_joined_auto", [("001002", 0.0), ("001003", 0.0)], None),
    _case(
        "basmala+067001_manual",
        [("001001", 0.3), ("067001", 0.0)],
        _text(67, 1, None, ("basmala",)),
    ),
    _case("basmala+067001_auto", [("001001", 0.3), ("067001", 0.0)], None),
    _case("001002_twice_manual", [("001002", 1.0), ("001002", 0.0)], _text(1, 2)),
    _case("001002_twice_auto", [("001002", 1.0), ("001002", 0.0)], None),
    _case(
        "112001-4_manual",
        [("112001", 0.0), ("112002", 0.0), ("112003", 0.0), ("112004", 0.0)],
        _text(112, 1, 4),
    ),  # fmt: skip
    _case("wrong_text_manual", [("001002", 0.0)], _text(1, 3)),
]


def audio_file(key: str) -> pathlib.Path:
    """The Husary mp3 for an ayah (SSSAAA), fetched once from our bucket into .cache/."""
    path = AUDIO_DIR / f"{key}.mp3"
    if not path.exists():
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(BUCKET + f"{key}.mp3", timeout=60) as r:
            path.write_bytes(r.read())
    return path
