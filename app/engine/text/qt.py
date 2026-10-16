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
    PhoneticSearch,
    QuranPhoneticScriptOutput,
    ReciterError,
    chunck_phonemes,
    explain_error,
    quran_phonetizer,
)
from quran_transcript.phonetics.error_explainer import (
    extract_ref_phonetic_to_uthmani,
    get_ref_phonetic_groups_tajweed_rules,
)
from quran_transcript.phonetics.moshaf_attributes import get_arabic_attributes, get_arabic_name
from quran_transcript.phonetics.search import NoPhonemesSearchResult
from quran_transcript.phonetics.sifa import parse_tafkheem_sifa
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
    "NoPhonemesSearchResult",
    "PhoneticSearch",
    "ReciterError",
    "extract_ref_phonetic_to_uthmani",
    "get_ref_phonetic_groups_tajweed_rules",
    "parse_tafkheem_sifa",
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
