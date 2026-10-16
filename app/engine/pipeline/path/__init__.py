"""Where the reciter stopped, went back, or joined ayat: the recitation path.

Ported from tajweed_ai `muaalem_lab/path.py` (rules: tajweed_ai docs/project-log.md 9.3 as
corrected in the 2026-10-13 audit):
- A real pause (≥ pauses.MIN_PAUSE_S) is a stop. The search never decides "carried on" at a real
  pause: that would erase a stop on a full haraka, or a wasl on a sukoon.
- After a stop it decides only where the reciter resumed: the next word, or any earlier word back
  to the start of the previous ayah.
- Going back is accepted only when the repeated words are heard again: every candidate is scored
  by the edit distance between what was heard and its phonetic script.
- Each stretch without a stop is phonetized as a whole, never stitched from words.
- A short silence (SOFT_PAUSE_S..MIN_PAUSE_S) at an ayah end may or may not be a stop: the better
  fit wins, marked uncertain.
- At the four sakt places a pause is a stop and no pause is the sakt.
- Where several connected ways are all correct (rules.connected_alternatives: «مَالِيَهْ ۜ هَلَكَ»),
  each is tried and the one heard is kept.

`infer` is the entry point (search.py).
"""

from app.engine.pipeline.path.result import Boundary, Inferred
from app.engine.pipeline.path.search import infer

__all__ = ["Boundary", "Inferred", "infer"]
