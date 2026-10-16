"""The GPU part: loading the two pinned models and running their forward passes.

Ported from tajweed_ai `muaalem_lab/model.py`, `pauses.py` (Segmenter) and `decode.py`
(frame_probs). Loaded from the local pinned snapshots, so they never contact the hub.
"""
