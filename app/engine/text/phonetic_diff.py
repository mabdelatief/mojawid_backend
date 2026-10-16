"""The diff between the expected and the heard phonetic scripts, in whole letter groups.

Ported from tajweed_ai `muaalem_lab/analysis.py` (phoneme_diff, _group_bounds) and
`labels.blocks`. The lab's `extend` closure is the _Blocks class here, same steps.
"""

from typing import Any

import Levenshtein

from app.engine.text.qt import chunck_phonemes

Block = dict[str, Any]


def group_bounds(phonemes: str) -> set[int]:
    """Every position where a letter group starts or ends."""
    bounds, pos = {0, len(phonemes)}, 0
    for g in chunck_phonemes(phonemes):
        pos = phonemes.find(g, pos) + len(g)
        bounds.add(pos)
    return bounds


class _Blocks:
    """Collects opcodes into blocks that close only on a boundary both sides share."""

    def __init__(self, ref: str, pred: str) -> None:
        self.ref_b, self.pred_b = group_bounds(ref), group_bounds(pred)
        self.blocks: list[Block] = []
        self.cur: Block | None = None

    def extend(self, i: tuple[int, int], j: tuple[int, int], change: Block | None) -> None:
        if self.cur is None:
            self.cur = {"ref": [i[0], i[0]], "pred": [j[0], j[0]], "ops": []}
        self.cur["ref"][1], self.cur["pred"][1] = i[1], j[1]
        if change:
            self.cur["ops"].append(change)
        if i[1] in self.ref_b and j[1] in self.pred_b:
            self.blocks.append(self.cur)
            self.cur = None

    def finish(self) -> list[Block]:
        if self.cur is not None:
            self.blocks.append(self.cur)
        return self.blocks


def _raw_blocks(ref: str, pred: str) -> list[Block]:
    acc = _Blocks(ref, pred)
    for tag, i1, i2, j1, j2 in Levenshtein.opcodes(ref, pred):
        if tag == "equal":
            # walk the run one character at a time so a block can close at any boundary the two
            # sides share, not only at the end of the run
            for k in range(i2 - i1):
                acc.extend((i1 + k, i1 + k + 1), (j1 + k, j1 + k + 1), None)
        else:
            acc.extend((i1, i2), (j1, j2), {"op": tag, "ref": ref[i1:i2], "pred": pred[j1:j2]})
    return acc.finish()


def phoneme_diff(ref: str, pred: str) -> list[Block]:
    """Character-level edit opcodes, merged so every block starts and ends on a phoneme-group
    boundary on both sides (a letter is never split from its haraka)."""
    out: list[Block] = []
    for b in _raw_blocks(ref, pred):
        r, p = ref[b["ref"][0] : b["ref"][1]], pred[b["pred"][0] : b["pred"][1]]
        kinds = {c["op"] for c in b["ops"]}
        op = "equal" if not kinds else kinds.pop() if len(kinds) == 1 else "replace"
        if op == "equal" and out and out[-1]["op"] == "equal":
            out[-1]["ref"] += r
            out[-1]["pred"] += p
            out[-1]["ref_span"][1] = b["ref"][1]
            out[-1]["pred_span"][1] = b["pred"][1]
            continue
        out.append(
            {"op": op, "ref": r, "pred": p, "changes": b["ops"],
             "ref_span": list(b["ref"]), "pred_span": list(b["pred"])}
        )  # fmt: skip
    return out


def blocks(ref_phonemes: str, predicted: str) -> list[Block]:
    """The places where the heard script differs from the expected one, each covering whole
    letter groups on both sides."""
    keys = ("ref_span", "pred_span", "ref", "pred", "op", "changes")
    return [
        {k: b[k] for k in keys} for b in phoneme_diff(ref_phonemes, predicted) if b["op"] != "equal"
    ]
