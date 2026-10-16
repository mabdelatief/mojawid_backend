"""Loading the models and running them, one request at a time on one GPU.

Ported from tajweed_ai `muaalem_lab/model.py` (load_model, LoadedModel, _warm_up) and
`decode.frame_probs`. The lab held its lock through the CPU decoding too; here the lock covers
only the two forward passes, and decoding (a Python alignment loop) runs outside it.
"""

import dataclasses
import logging
import threading
import time
from typing import Any

import numpy as np
import torch

from app.engine.pipeline.decode import decode
from app.engine.pipeline.heard import Heard
from app.engine.pipeline.models.segmenter import Segmenter
from app.engine.pipeline.models.snapshots import model_path
from app.engine.pipeline.pauses import SAMPLE_RATE, pauses_from_labels
from app.engine.pipeline.qm import Muaalem
from app.model_pins import MUAALEM, SEGMENTER

log = logging.getLogger("mojawid.worker.model")


@dataclasses.dataclass(frozen=True)
class ModelOutput:
    """The raw outputs of one run: per-frame probabilities of all 11 outputs, segmenter labels."""

    probs: dict[str, np.ndarray]
    labels: np.ndarray
    model_ms: int


@torch.no_grad()
def frame_probs(muaalem: Any, wave: np.ndarray) -> dict[str, np.ndarray]:
    """Per-frame class probabilities for every output, (T, C) float32, softmax in float32."""
    feats = muaalem.processor([wave], sampling_rate=SAMPLE_RATE, return_tensors="pt")
    feats = {
        k: v.to(muaalem.device, dtype=muaalem.dtype if v.is_floating_point() else v.dtype)
        for k, v in feats.items()
    }
    logits = muaalem.model(**feats, return_dict=False)[0]
    return {level: torch.softmax(x[0].float(), dim=-1).cpu().numpy() for level, x in logits.items()}


class GpuRunner:
    """The loaded models. `infer` is serialised; everything after it isn't."""

    def __init__(
        self, muaalem: Any, segmenter: Segmenter, dtype: torch.dtype, notes: list[str]
    ) -> None:
        self.muaalem, self.segmenter, self.dtype, self.notes = muaalem, segmenter, dtype, notes
        self.lock = threading.Lock()  # one GPU; never two forward passes at once
        tok = muaalem.multi_level_tokenizer
        self.id_to_vocab: dict[str, dict[int, str]] = tok.id_to_vocab
        self.sifat_to_en: dict[str, dict[int, str]] = tok.sifat_to_en_vocab

    @property
    def device(self) -> str:
        return str(self.muaalem.device)

    @property
    def dtype_name(self) -> str:
        return str(self.dtype).removeprefix("torch.")

    def infer(self, wave: np.ndarray) -> ModelOutput:
        """The segmenter's labels, then the recitation model's probabilities (the lab's order)."""
        with self.lock:
            t0 = time.perf_counter()
            labels = self.segmenter.frame_labels(wave)
            probs = frame_probs(self.muaalem, wave)
            if self.device == "cuda":
                torch.cuda.synchronize()
            return ModelOutput(probs, labels, round((time.perf_counter() - t0) * 1000))

    def heard(self, wave: np.ndarray) -> tuple[Heard, int]:
        """What the model heard, with the pauses, and the model time in ms."""
        out = self.infer(wave)
        heard = decode(out.probs, self.id_to_vocab, self.sifat_to_en)
        heard.pauses = pauses_from_labels(out.labels, len(wave))
        return heard, out.model_ms


def _warm_up(m: Any) -> None:
    """One forward pass on a second of noise, to prove the dtype works on this GPU."""
    wave = (np.random.default_rng(0).standard_normal(SAMPLE_RATE) * 0.01).astype(np.float32)
    for level, probs in frame_probs(m, wave).items():
        if not np.isfinite(probs).all():
            raise RuntimeError(f"non-finite output at level {level}")


def _dtypes(device: str, notes: list[str]) -> list[torch.dtype]:
    if device != "cuda":
        notes.append("CUDA not available; running on CPU in float32 (slow)")
        return [torch.float32]
    if not torch.cuda.is_bf16_supported():
        notes.append("GPU reports no bfloat16 support; skipped bf16")
        return [torch.float16, torch.float32]
    return [torch.bfloat16, torch.float16, torch.float32]


def load_runner(device: str | None = None) -> GpuRunner:
    """Load both pinned snapshots, on CUDA in bfloat16, falling back to float16 then float32."""
    path = str(model_path(MUAALEM))
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    notes: list[str] = []
    last_err: Exception | None = None
    for dtype in _dtypes(device, notes):
        try:
            m = Muaalem(model_name_or_path=path, device=device, dtype=dtype)
            _warm_up(m)
            pins = {"model": MUAALEM.revision, "segmenter": SEGMENTER.revision}
            log.info("models loaded", extra={"device": device, "dtype": str(dtype), **pins})
            return GpuRunner(m, Segmenter(device, dtype), dtype, notes)
        except Exception as exc:  # any failure here means: try the next dtype
            last_err = exc
            notes.append(f"{dtype} failed: {type(exc).__name__}; falling back")
            if device == "cuda":
                torch.cuda.empty_cache()
    raise RuntimeError("could not load the model in any dtype") from last_err
