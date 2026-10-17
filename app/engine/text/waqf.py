"""The Mushaf's waqf signs, by word, for display.

Our Quran text is Tanzil's edition without pause marks, so the signs come from a data file made
once from Tanzil's full edition of the same text (tools/import_waqf_signs.py, which has the
source and licence). They are shown on the words and never used to judge where a reciter
stopped: that would be a ruling for the teachers.
"""

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "waqf_signs.json"


@lru_cache(maxsize=1)
def _signs() -> dict[str, str]:
    loaded: dict[str, str] = json.loads(DATA.read_text(encoding="utf-8"))["signs"]
    return loaded


def waqf_signs(sura: int, aya: int, word: int) -> str | None:
    """The signs after this word, in Mushaf order (e.g. "ۖ", or "ۜۗ" in 36:52), or None."""
    return _signs().get(f"{sura}:{aya}:{word}")
