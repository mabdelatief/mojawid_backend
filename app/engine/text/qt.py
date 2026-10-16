"""The one place that imports quran-transcript (the patched 0.6.4+muaalem.1 in vendor/).

The package ships no type information, so its names are Any to mypy. Keeping every import here
means the rest of the engine depends on this module's names, and a version change is reviewed
in one place.
"""

import quran_transcript.alphabet as alph
from quran_transcript import (
    Aya,
    MappingPos,
    MoshafAttributes,
    QuranPhoneticScriptOutput,
    chunck_phonemes,
    explain_error,
    quran_phonetizer,
)
from quran_transcript.phonetics.moshaf_attributes import get_arabic_attributes, get_arabic_name
from quran_transcript.phonetics.tajweed_rulses import (
    AaredMaddRule,
    LazemMaddRule,
    LeenMaddRule,
    MonfaselMaddRule,
    MottaselMaddPauseRule,
    MottaselMaddRule,
    Qalqalah,
)

__all__ = [
    "AaredMaddRule",
    "Aya",
    "LazemMaddRule",
    "LeenMaddRule",
    "MappingPos",
    "MonfaselMaddRule",
    "MoshafAttributes",
    "MottaselMaddPauseRule",
    "MottaselMaddRule",
    "Qalqalah",
    "QuranPhoneticScriptOutput",
    "alph",
    "chunck_phonemes",
    "explain_error",
    "get_arabic_attributes",
    "get_arabic_name",
    "quran_phonetizer",
]
