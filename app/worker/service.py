"""One analysis in the worker: the upload → the result. Synchronous (CPU and GPU work); the app
runs it in a thread.

Order: the request is checked first (reading settings, text), so a bad one never wakes the GPU;
then the audio is decoded in memory, the models run, and the CPU pipeline makes the result. The
audio exists only in memory for the length of this call.
"""

import time
from importlib.metadata import version
from typing import Protocol

import numpy as np

from app.contracts.analysis import (
    AnalysisQuery,
    AnalysisResult,
    AnalysisWarning,
    EngineVersions,
    Summary,
    TextUsed,
    WordTime,
)
from app.engine.pipeline.audio import as_saved, decode_audio
from app.engine.pipeline.errors import InvalidTextSelection
from app.engine.pipeline.heard import Heard
from app.engine.pipeline.pauses import SAMPLE_RATE
from app.engine.pipeline.run import Job, Outcome, analyse, validate
from app.engine.text import rules as R
from app.engine.text.structure import TextSelection
from app.model_pins import MUAALEM, SEGMENTER


class Runner(Protocol):
    """What the service needs from the models (GpuRunner, or a fake in tests)."""

    def heard(self, wave: np.ndarray) -> tuple[Heard, int]: ...


def job_from(query: AnalysisQuery) -> Job:
    """The engine's job for a request. InvalidTextSelection when manual mode lacks the text."""
    prefixes = tuple(
        p for p, on in (("istiaatha", query.istiaatha), ("basmala", query.basmala)) if on
    )
    if query.mode == "auto":
        hint = (query.sura, query.aya_end) if query.sura and query.aya_end else None
        return Job(text=None, reading=query.reading_settings(), raum=query.raum, hint=hint)
    if query.sura is None or query.aya_start is None:
        raise InvalidTextSelection("Manual mode needs sura and aya_start.")
    text = TextSelection(
        query.sura, query.aya_start, query.aya_end or query.aya_start, prefixes=prefixes
    )
    return Job(text=text, reading=query.reading_settings(), raum=query.raum)


def _summary(outcome: Outcome) -> Summary:
    rows = outcome.report["errors"]
    return Summary(
        mistakes=sum(1 for r in rows if r["counted"]),
        uncertain=sum(1 for r in rows if r["mark"] == "uncertain"),
        exact_match=bool(outcome.report["exact_match"]),
    )


def to_result(outcome: Outcome, duration_s: float, timings_ms: dict[str, int]) -> AnalysisResult:
    t = outcome.text
    return AnalysisResult(
        mode="auto" if outcome.mode == "auto" else "manual",
        text=TextUsed(
            sura=t.sura,
            aya_start=t.aya_start,
            aya_end=t.aya_end or t.aya_start,
            prefixes=list(t.prefixes),
        ),
        duration_s=round(duration_s, 3),
        summary=_summary(outcome),
        detection=outcome.detection,
        path=outcome.path,
        warnings=[AnalysisWarning.model_validate(w) for w in outcome.warnings],
        word_times=[WordTime.model_validate(w) for w in outcome.word_times],
        report=outcome.report,
        engine=EngineVersions(
            model_revision=MUAALEM.revision,
            segmenter_revision=SEGMENTER.revision,
            quran_transcript=version("quran-transcript"),
            rules=R.DEFAULT.name,
        ),
        timings_ms=timings_ms,
    )


class WorkerService:
    def __init__(self, runner: Runner) -> None:
        self.runner = runner

    def analyse_wave(self, job: Job, wave: np.ndarray) -> AnalysisResult:
        """The result for a decoded, 16-bit-rounded waveform."""
        t0 = time.perf_counter()
        heard, model_ms = self.runner.heard(wave)
        duration_s = wave.size / SAMPLE_RATE
        outcome = analyse(job, heard, duration_s)
        total = round((time.perf_counter() - t0) * 1000)
        return to_result(outcome, duration_s, {"model": model_ms, "total": total})

    def analyse_upload(self, audio: bytes, query: AnalysisQuery) -> AnalysisResult:
        """The result for an upload. Raises the engine's AnalysisError subclasses."""
        job = job_from(query)
        validate(job)  # before the GPU: a bad request never wakes it
        wave = as_saved(decode_audio(audio))
        return self.analyse_wave(job, wave)
