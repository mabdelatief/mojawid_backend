"""How sure the model was at each place where what it heard differs from the expected text.

Ported from tajweed_ai `muaalem_lab/doubt.py`. The heard script is the model's top symbol per
40 ms frame; where the model was split almost evenly that top symbol is a coin flip (on the user's
Al-Insan 9 recording, 2026-10-14, the qalqalah of «نُطْعِمُكُمْ» lost to "nothing" by 0.479 to
0.510 and showed as a definite mistake).

For each differing place this compares how likely the model finds what it heard with how likely
it finds the expected reading, over that place's frames (CTC, every alignment summed, torch's
ctc_loss on CPU in float64, exactly as the lab). Measured on the stored recordings (124 flagged
places, 2026-10-14): 18 under 10×, nothing between 7.7× and 14×, most at 20× and more. A place
under DOUBT_RATIO is uncertain: shown, never counted as a mistake. To be re-measured against the
teachers' reviews.
"""

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import torch

from app.engine.pipeline.ctc import BLANK, Token, ctc_greedy

DOUBT_RATIO = 10.0
_FLOOR = 1e-12


def _nll(logp: torch.Tensor, labels: list[int]) -> float:
    """Negative log-likelihood of `labels` over these frames, all CTC alignments summed;
    infinite when they cannot fit."""
    if not labels:
        return float(-logp[:, BLANK].sum())
    return float(
        torch.nn.functional.ctc_loss(
            logp.unsqueeze(1),
            torch.tensor([labels]),
            torch.tensor([logp.shape[0]]),
            torch.tensor([len(labels)]),
            blank=BLANK,
            reduction="sum",
            zero_infinity=False,
        )
    )


def _frames(tokens: list[Token], span: tuple[int, int], n: int) -> tuple[int, int, int, int]:
    """The place's frames, from the heard letter before it to the one after (and that context)."""
    j1, j2 = span
    left, right = max(0, j1 - 1), min(len(tokens), j2 + 1)
    f0 = tokens[left].start if left < j1 else 0
    f1 = tokens[right - 1].end if right > j2 else n
    if not tokens:
        f0, f1 = 0, n
    return f0, f1, left, right


def _ratio(
    block: dict[str, Any], ctx: tuple[torch.Tensor, list[Token], str, dict[str, int]]
) -> float:
    logp, tokens, heard, to_id = ctx
    j1, j2 = block["pred_span"]
    f0, f1, left, right = _frames(tokens, (j1, j2), logp.shape[0])
    before, after = heard[left:j1], heard[j2:right]
    try:
        expected = _nll(logp[f0:f1], [to_id[c] for c in before + block["ref"] + after])
        got = _nll(logp[f0:f1], [to_id[c] for c in before + block["pred"] + after])
    except KeyError:  # a symbol this model does not have
        return math.inf
    return math.exp(min(expected - got, 700.0)) if math.isfinite(expected) else math.inf


def ratios(
    probs: np.ndarray, vocab: Sequence[str], heard: str, blocks: list[dict[str, Any]]
) -> list[float] | None:
    """Per diff block ("equal" ones included and given inf): how many times more likely the heard
    reading is than the expected one. None when `probs` don't decode to `heard`."""
    tokens = ctc_greedy(probs)
    if "".join(vocab[t.id] for t in tokens) != heard:
        return None
    to_id = {v: k for k, v in enumerate(vocab) if k != BLANK}
    logp = torch.from_numpy(np.log(np.clip(probs.astype(np.float64), _FLOOR, 1.0)))
    ctx = (logp, tokens, heard, to_id)
    return [math.inf if b["op"] == "equal" else _ratio(b, ctx) for b in blocks]


def is_uncertain(ratio: float | None) -> bool:
    """Under DOUBT_RATIO: a near coin flip, not a mistake."""
    return ratio is not None and ratio < DOUBT_RATIO
