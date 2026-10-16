"""The one place the engine imports quran-muaalem (0.2.2; untyped; importing it loads torch).

Used: its Arabic names for sifat values, and (in models/) its model class and tokenizer. Not used:
its decoding (pipeline/decode.py replaces it) or its group alignment for the sifat table, whose
merge_same_phoneme_group pairs a letter with its neighbour (analysis/sifat.py replaces it).
"""

from quran_muaalem import Muaalem
from quran_muaalem.modeling.vocab import SIFAT_ATTR_TO_ARABIC_WITHOUT_BRACKETS

__all__ = ["SIFAT_ATTR_TO_ARABIC_WITHOUT_BRACKETS", "Muaalem"]
