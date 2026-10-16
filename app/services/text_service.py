"""Meta and reference text, from the engine's text side (CPU only, no database).

The engine is synchronous and CPU-bound, so reference building runs in a worker thread; its
results are cached by the engine (phonetizer and Quran lookups).
"""

import asyncio
from functools import lru_cache
from importlib.metadata import version

from fastapi import status

from app.config import Settings
from app.contracts import text as C
from app.engine.text import rules as R
from app.engine.text.boundaries import special_boundaries
from app.engine.text.moshaf import ReadingOption, moshaf_all_options, moshaf_from_dict
from app.engine.text.quran_text import surah_list
from app.engine.text.readable import harakat
from app.engine.text.reference import build_reference
from app.engine.text.structure import TextSelection
from app.engine.text.tajweed import CLASSES, classes_present, tajweed_spans
from app.errors import AppError

MAX_RECORDING_SECONDS = 60
SOFT_RECORDING_SECONDS = 30
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def warm_up() -> None:
    """Load the Quran and scan it for special boundaries (a few seconds), so the first request
    doesn't pay for it. Called from the API lifespan."""
    surah_list()
    special_boundaries()


def _choice_label(option: ReadingOption, value: R.Value) -> str:
    label = option.choice_labels_ar.get(value)
    if label:
        return str(label)
    return harakat(value) if isinstance(value, int) else str(value)


def _setting(option: ReadingOption) -> C.ReadingSetting:
    return C.ReadingSetting(
        name=option.name,
        label_ar=option.label_ar,
        choices=[
            C.ReadingChoice(value=v, label_ar=_choice_label(option, v)) for v in option.choices
        ],
        default=option.default,
        main=option.main,
    )


@lru_cache(maxsize=4)
def _meta(max_ayat_manual: int) -> C.Meta:
    return C.Meta(
        reading=[_setting(o) for o in moshaf_all_options()],
        practices=dict(R.DEFAULT.practices),
        surahs=[C.SurahInfo(index=s.index, name=s.name, ayat=s.ayat) for s in surah_list()],
        limits=C.Limits(
            max_recording_seconds=MAX_RECORDING_SECONDS,
            soft_recording_seconds=SOFT_RECORDING_SECONDS,
            max_upload_bytes=MAX_UPLOAD_BYTES,
            max_ayat_manual=max_ayat_manual,
        ),
        tajweed_classes=list(CLASSES),
        engine=C.EngineInfo(quran_transcript=version("quran-transcript"), rules=R.DEFAULT.name),
    )


def _reference(req: C.ReferenceRequest) -> C.Reference:
    try:
        moshaf = moshaf_from_dict(req.reading)
    except ValueError as exc:  # also pydantic's ValidationError for an impossible value
        raise AppError(
            "invalid_reading_settings", "Those reading settings aren't allowed."
        ) from exc
    text = TextSelection(req.sura, req.aya_start, req.aya_end, prefixes=tuple(req.prefixes))
    try:
        ref = build_reference(text, moshaf)
    except ValueError as exc:
        raise AppError("invalid_text_selection", "Those ayat aren't in this surah.") from exc
    spans = tajweed_spans(ref.uthmani, ref.phonetic)
    segments = [
        C.ReferenceSegment(
            kind=s.kind,
            start=s.start,
            end=s.end,
            words=[C.ReferenceWord(**vars(w)) for w in s.words],
        )
        for s in ref.segments
    ]
    return C.Reference(
        uthmani=ref.uthmani,
        segments=segments,
        tajweed=[(s, t, cls) for s, t, cls in spans],
        classes_present=classes_present(spans),
    )


class TextService:
    """Meta and reference text."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def meta(self) -> C.Meta:
        return _meta(self.settings.max_ayat_manual)

    async def reference(self, req: C.ReferenceRequest) -> C.Reference:
        """The reference for whole ayat. Errors: too_many_ayat, invalid_text_selection,
        invalid_reading_settings."""
        if req.aya_end < req.aya_start:
            raise AppError("invalid_text_selection", "The ayah range runs backwards.")
        if req.aya_end - req.aya_start + 1 > self.settings.max_ayat_manual:
            raise AppError(
                "too_many_ayat",
                f"At most {self.settings.max_ayat_manual} ayat per request.",
                status.HTTP_400_BAD_REQUEST,
            )
        return await asyncio.to_thread(_reference, req)
