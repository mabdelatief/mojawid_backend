"""Greedy CTC over the model's per-frame probabilities, and each letter group's frames.

Ported from tajweed_ai `muaalem_lab/decode.py` (Token, ctc_greedy, group_frames). The model
output has 25 frames per second (40 ms), the same grid for every output.
"""

import dataclasses

import numpy as np

BLANK = 0
FRAME_SECONDS = 0.04


@dataclasses.dataclass(frozen=True)
class Token:
    """A run of one non-blank class."""

    id: int
    start: int  # first frame of the run
    end: int  # one past the last frame
    prob: float  # mean top-1 probability over the run


def ctc_greedy(probs: np.ndarray, blank: int = BLANK) -> list[Token]:
    """Best class per frame; each run of one non-blank class is a token. Two runs of the same
    class separated by a blank are two tokens. (quran-muaalem's own decode drops a final
    one-frame letter that follows a blank; this doesn't.)"""
    ids = probs.argmax(axis=1)
    top = probs.max(axis=1)
    tokens, t, n = [], 0, len(ids)
    while t < n:
        u = t
        while u < n and ids[u] == ids[t]:
            u += 1
        if ids[t] != blank:
            tokens.append(Token(int(ids[t]), t, u, float(top[t:u].mean())))
        t = u
    return tokens


def group_frames(groups: list[str], tokens: list[Token]) -> list[tuple[int, int]]:
    """Frame span of each letter group: from its first character's run to its last one's."""
    spans, k = [], 0
    for g in groups:
        spans.append((tokens[k].start, tokens[k + len(g) - 1].end))
        k += len(g)
    return spans
