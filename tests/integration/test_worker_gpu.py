"""L2 goldens: the worker's whole pipeline, real models on this machine's GPU, against the lab's
results on the same Husary recordings (tests/golden/pipeline/). Run on demand:

    .venv/bin/pytest -m gpu tests/integration -q

Skipped without CUDA or the pinned snapshots. The audio is built the way the golden generator
built it (each ayah file decoded, silences added, rounded to 16 bit), but decoded by the port,
from memory.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.engine.pipeline.audio import as_saved, decode_audio
from app.worker.service import WorkerService
from tests.unit.engine.test_pipeline_golden import CASES, job_for, plain, without_new_fields
from tools.golden.pipeline_cases import audio_file

pytestmark = pytest.mark.gpu


@pytest.fixture(scope="module")
def service() -> Iterator[WorkerService]:
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("no CUDA")
    from app.engine.pipeline.models.gpu import load_runner

    try:
        t0 = time.perf_counter()
        runner = load_runner()
        took = time.perf_counter() - t0
        print(f"models loaded in {took:.1f} s on {runner.device} ({runner.dtype_name})")
    except FileNotFoundError as exc:
        pytest.skip(str(exc))
    yield WorkerService(runner)


def wave_for(case: dict[str, Any]) -> np.ndarray:
    parts = []
    for key, silence in case["audio"]:
        parts.append(decode_audio(audio_file(key).read_bytes()))
        parts.append(np.zeros(int(round(silence * 16000)), dtype=np.float32))
    return as_saved(np.concatenate(parts))


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_gpu_result_matches_the_lab(service: WorkerService, path: Path) -> None:
    golden = json.loads(path.read_text())
    result = service.analyse_wave(job_for(golden["case"]), wave_for(golden["case"]))
    t = result.timings_ms
    print(f"{golden['case']['id']:28s} model {t['model']:4d} ms, total {t['total']:4d} ms")
    assert result.report["predicted_phonemes"] == golden["heard"]
    theirs = dict(golden["report"])
    theirs.pop("sifat_unreliable_probs")
    assert without_new_fields(result.report) == theirs
    assert result.detection == golden["detection"]
    assert plain(result.path) == golden["path"]
