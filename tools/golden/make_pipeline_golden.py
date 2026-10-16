"""Make the pipeline goldens: tajweed_ai's own analysis of each case in pipeline_cases.py, with
the model's raw outputs, so the port can be checked on the CPU (L1, exact). Runs in tajweed_ai's
environment, on the GPU, from this repo's root:

    uv run --project ../tajweed_ai python -m tools.golden.make_pipeline_golden [--lab ../tajweed_ai]

For each case it writes to tests/golden/pipeline/ (committed): <id>.npz (the frame probabilities
of all 11 outputs and the segmenter's frame labels) and <id>.json (the case, the heard script, the
report, detection, path, warnings, or the error). It reproduces the lab's `/test` flow
(collect_api) step by step without storing anything: MUAALEM_DATA_DIR points at an empty scratch
folder.
"""

import argparse
import importlib
import json
import os
import sys
import tempfile
from typing import Any

import numpy as np

from tools.golden.pipeline_cases import CASES, GOLDEN_DIR, REPO, audio_file


def _lab(path: str) -> dict[str, Any]:
    os.environ["MUAALEM_DATA_DIR"] = tempfile.mkdtemp(prefix="mojawid-golden-")
    sys.path.append(path)
    names = ("audio", "model", "decode", "pauses", "quran", "detect", "analysis", "collect_api")
    return {n: importlib.import_module(f"muaalem_lab.{n}") for n in names}


def _wave(lab: dict[str, Any], audio: list[list[Any]]) -> np.ndarray:
    parts = []
    for key, silence in audio:
        parts.append(lab["audio"].decode_to_16k_mono(audio_file(key), 600))
        parts.append(np.zeros(int(round(silence * 16000)), dtype=np.float32))
    return lab["collect_api"]._as_saved(np.concatenate(parts))


def _model_outputs(
    lab: dict[str, Any], m: Any, wave: np.ndarray
) -> tuple[Any, dict[str, np.ndarray], np.ndarray]:
    labels = m.segmenter.frame_labels(wave)
    probs = lab["decode"].frame_probs(m.muaalem, wave)
    tok = m.muaalem.multi_level_tokenizer
    out = lab["decode"].decode(probs, tok.id_to_vocab, tok.sifat_to_en_vocab)
    out.pauses = lab["pauses"].pauses_from_labels(labels, len(wave))
    return out, probs, labels


def _analyse(lab: dict[str, Any], case: dict[str, Any], out: Any) -> dict[str, Any]:
    """The lab's /test flow (manual or auto), without storage."""
    A, quran = lab["collect_api"], lab["quran"]
    moshaf = quran.moshaf_from_dict(case["reading"])
    detection, detected_path, text_d = None, None, case["text"]
    if text_d is None:
        if not out.phonemes.text.strip():
            return {"error": "no_recitation_heard"}
        det = lab["detect"].detect(out.phonemes.text, moshaf, None)
        if det is None:
            return {"error": "ayah_not_recognised"}
        text_d, cands, clear, detected_path = A._choose_range(
            det, {"prefixes": list(det.prefixes)}, moshaf, out
        )
        detection = {"clear": clear, "prefixes": list(det.prefixes), "candidates": cands}
    st = A._structure_from({"text": text_d}, moshaf)
    ref = quran.build_reference_from_structure(st, moshaf)
    inferred = detected_path or A._infer_path(st, moshaf, out)
    if inferred is not None:
        ref = quran.build_reference_from_structure(inferred.structure, moshaf)
    report, _ = lab["analysis"].analyze(out, ref, case["raum"])
    text = {k: text_d.get(k) for k in ("sura", "aya_start", "aya_end", "prefixes")}
    return {"error": None, "text": text, "report": report, "detection": detection,
            "path": inferred.to_json() if inferred is not None else None}  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lab", default=str(REPO.parent / "tajweed_ai"))
    args = parser.parse_args()
    lab = _lab(args.lab)
    m = lab["model"].load_model()
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    tok = m.muaalem.multi_level_tokenizer
    vocab = {"id_to_vocab": tok.id_to_vocab, "sifat_to_en_vocab": tok.sifat_to_en_vocab}
    (GOLDEN_DIR / "vocab.json").write_text(json.dumps(vocab, ensure_ascii=False))
    for case in CASES:
        wave = _wave(lab, case["audio"])
        out, probs, labels = _model_outputs(lab, m, wave)
        np.savez_compressed(GOLDEN_DIR / f"{case['id']}.npz", segmenter_labels=labels, **probs)
        result = _analyse(lab, case, out)
        edges = {
            "starts_in_speech": out.pauses.starts_in_speech,
            "ends_in_speech": out.pauses.ends_in_speech,
        }
        golden = {
            "case": case, "n_samples": len(wave), "heard": out.phonemes.text,
            "group_frames": [list(x) for x in out.group_frames],
            "pauses": edges,
            "model": {"revision": m.revision, "dtype": m.dtype_name}, **result,
        }  # fmt: skip
        (GOLDEN_DIR / f"{case['id']}.json").write_text(
            json.dumps(golden, ensure_ascii=False, default=list)
        )
        print(f"{case['id']:28s} heard {len(out.phonemes.text):4d} chars  error={result['error']}")


if __name__ == "__main__":
    main()
