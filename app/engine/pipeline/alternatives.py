"""Words read more than one correct way whatever the reciter set beforehand (rules.alternatives):
ضعف in al-Rum (fath or damm), تأمنا (ishmam or rawm), ءآلذكرين / ءآلآن / ءآلله (madd or tasheel),
and starting with ٱلِٱسْمُ («أَلِسْمُ» or «لِسْمُ»). Al-Shatibiyya gives Hafs each way, so the
expected reading follows the way that was heard (audit 2026-10-16, R4 and R9).

For each such word in the recited text, the reference is rebuilt with every value, and the one
closest to what was heard (edit distance on the phonetic script) is kept; a tie keeps the
reciter's own setting.
"""

import re
import unicodedata
from typing import Any

import Levenshtein

from app.engine.text import rules as R
from app.engine.text.qt import alph
from app.engine.text.reference import Reference, build_reference_from_structure


def word_present(alt: R.Alternative, ref: Reference) -> bool:
    if alt.suras and ref.sura not in alt.suras:
        return False
    # the Quran text keeps «آ» as alif + maddah; the phonetizer's patterns use the composed form
    text = unicodedata.normalize("NFC", ref.uthmani)
    return any(
        c.attr_name == alt.field and re.search(unicodedata.normalize("NFC", c.pattern), text)
        for c in alph.uthmani.special_patterns
    )


def closest_reading(ref: Reference, moshaf: Any, heard: str) -> Reference:
    """The reference with each such word read the way closest to what was heard."""
    best = ref
    for alt in R.DEFAULT.alternatives:
        if not word_present(alt, best):
            continue
        current = getattr(moshaf, alt.field)
        scored = []
        for value in dict.fromkeys((current, *alt.values)):
            m = moshaf.model_copy(update={alt.field: value})
            cand = best if value == current else build_reference_from_structure(ref.structure, m)
            dist = Levenshtein.distance(cand.phonetic.phonemes, heard)
            scored.append((dist, value != current, value, cand))
        _, _, value, best = min(scored, key=lambda x: (x[0], x[1]))
        moshaf = moshaf.model_copy(update={alt.field: value})
    return best
