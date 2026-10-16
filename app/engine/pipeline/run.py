"""One analysis, from what the model heard to the result: the lab's `/test` flow without storage.

Ported from tajweed_ai `muaalem_lab/collect_api.py` (test, _structure_from, _result). Manual mode
checks the chosen text; auto mode detects it. Then the recitation path is inferred (where the
reciter stopped or went back), the reference is rebuilt on that path, and the report is made once
(the lab built it twice and the reference three times).

`validate` runs before the model, so a bad request never wakes the GPU.
"""

import dataclasses
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from app.engine.pipeline.alternatives import closest_reading
from app.engine.pipeline.analysis.report import analyze
from app.engine.pipeline.choose_range import choose_range, infer_path
from app.engine.pipeline.detect import detect
from app.engine.pipeline.errors import (
    AyahNotRecognised,
    InvalidReadingSettings,
    InvalidTextSelection,
    NoRecitationHeard,
)
from app.engine.pipeline.extras.rows import add_row_fields
from app.engine.pipeline.extras.word_times import word_times
from app.engine.pipeline.heard import Heard
from app.engine.pipeline.warnings import warnings
from app.engine.text.moshaf import moshaf_from_dict
from app.engine.text.reference import Reference, build_reference_from_structure
from app.engine.text.structure import TextSelection, default_structure


@dataclasses.dataclass(frozen=True)
class Job:
    """What to analyse: the chosen text (None: auto mode), the reading settings, raum practice,
    and in auto mode an optional hint (the text recited last, to prefer reading in order)."""

    text: TextSelection | None
    reading: Mapping[str, object]
    raum: bool = False
    hint: tuple[int, int] | None = None


@dataclasses.dataclass
class Outcome:
    """The result of one analysis."""

    mode: str  # "manual" | "auto"
    text: TextSelection
    report: dict[str, Any]
    detection: dict[str, Any] | None
    path: dict[str, Any] | None
    warnings: list[dict[str, Any]]
    word_times: list[dict[str, Any]]  # each recited word's span in the user's recording
    reference: Reference


def _moshaf(job: Job) -> Any:
    try:
        return moshaf_from_dict(job.reading)
    except (ValidationError, ValueError) as exc:
        raise InvalidReadingSettings(str(exc)) from exc


def _reference_for(text: TextSelection, moshaf: Any) -> Reference:
    try:
        return build_reference_from_structure(default_structure(text, moshaf), moshaf)
    except ValueError as exc:
        raise InvalidTextSelection(str(exc)) from exc


def validate(job: Job) -> Any:
    """The reading settings (and in manual mode the text), checked before the model runs.
    Returns the moshaf."""
    moshaf = _moshaf(job)
    if job.text is not None:
        _reference_for(job.text, moshaf)
    return moshaf


def _detect(
    heard: Heard, moshaf: Any, hint: tuple[int, int] | None
) -> tuple[TextSelection, dict[str, Any], Any]:
    if not heard.text.strip():
        raise NoRecitationHeard("No recitation was heard in the recording.")
    det = detect(heard.text, moshaf, hint)
    if det is None:
        raise AyahNotRecognised("The recitation doesn't match any ayah.")
    text, candidates, clear, inferred = choose_range(det, moshaf, heard)
    detection = {"clear": clear, "prefixes": list(det.prefixes), "candidates": candidates}
    return text, detection, inferred


def analyse(job: Job, heard: Heard, duration_s: float) -> Outcome:
    """The result for what the model heard (the CPU part after the model)."""
    moshaf = validate(job)
    detection, inferred = None, None
    if job.text is None:
        text, detection, inferred = _detect(heard, moshaf, job.hint)
    else:
        text = job.text
    ref = _reference_for(text, moshaf)
    inferred = inferred or infer_path(text, moshaf, heard)
    if inferred is not None:
        ref = build_reference_from_structure(inferred.structure, moshaf)
    ref = closest_reading(ref, moshaf, heard.text)
    report = analyze(heard, ref, job.raum)
    add_row_fields(report["errors"], ref)
    return Outcome(
        mode="auto" if job.text is None else "manual",
        text=text,
        report=report,
        detection=detection,
        path=inferred.to_json() if inferred is not None else None,
        warnings=warnings(heard.pauses, duration_s),
        word_times=word_times(heard, ref, report["diff"], duration_s),
        reference=ref,
    )
