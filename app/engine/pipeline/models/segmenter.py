"""The pause model: obadx/recitation-segmenter-v2 (MIT), speech or silence per 20 ms frame.

Ported from tajweed_ai `muaalem_lab/pauses.py` (Segmenter). Used directly, without its
`recitations-segmenter` package (which only adds torchaudio for reading files); the frame logic
follows that package's v1.0.0. The lock is GpuRunner's, not the segmenter's own.
"""

from typing import Any

import numpy as np
import torch
from transformers import AutoFeatureExtractor, Wav2Vec2BertForAudioFrameClassification

from app.engine.pipeline.models.snapshots import model_path
from app.engine.pipeline.pauses import FRAME_SAMPLES, SAMPLE_RATE
from app.model_pins import SEGMENTER

CHUNK_SAMPLES = 319_920  # 19.995 s: the longest input the segmenter was trained on


class Segmenter:
    """Speech/silence labels for a whole clip."""

    def __init__(self, device: str, dtype: torch.dtype) -> None:
        path = str(model_path(SEGMENTER))
        self.device, self.dtype = device, dtype
        self.processor: Any = AutoFeatureExtractor.from_pretrained(
            path, revision=SEGMENTER.revision
        )
        model = Wav2Vec2BertForAudioFrameClassification.from_pretrained(
            path, revision=SEGMENTER.revision
        )
        self.model: Any = model.to(device, dtype=dtype)
        self.model.eval()

    def _chunk_labels(self, chunk: np.ndarray) -> np.ndarray:
        n_frames = int(np.ceil(len(chunk) / FRAME_SAMPLES))
        feats = self.processor([chunk], sampling_rate=SAMPLE_RATE, return_tensors="pt")
        feats = {
            k: v.to(self.device, dtype=self.dtype if v.is_floating_point() else v.dtype)
            for k, v in feats.items()
        }
        lab: np.ndarray = self.model(**feats).logits[0].float().argmax(-1).cpu().numpy()
        # the feature extractor drops a partial last frame; the clip's tail takes the last label
        if len(lab) < n_frames:
            lab = np.concatenate([lab, np.full(n_frames - len(lab), lab[-1] if len(lab) else 0)])
        return lab[:n_frames]

    @torch.no_grad()
    def frame_labels(self, wave: np.ndarray) -> np.ndarray:
        """Speech (1) or silence (0) per 20 ms frame of the whole clip, in equal chunks of at most
        CHUNK_SAMPLES (so no chunk is a sliver the feature extractor cannot frame)."""
        n_chunks = max(1, int(np.ceil(len(wave) / CHUNK_SAMPLES)))
        size = int(np.ceil(len(wave) / n_chunks / FRAME_SAMPLES)) * FRAME_SAMPLES
        labels = [self._chunk_labels(wave[a : a + size]) for a in range(0, len(wave), size)]
        return np.concatenate(labels) if labels else np.zeros(0, dtype=int)
