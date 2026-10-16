"""Meta (settings, surahs, limits) and the reference text for chosen ayat."""

from typing import Literal

from pydantic import BaseModel, Field

Opening = Literal["istiaatha", "basmala"]
TajweedClass = Literal["madd6", "wajib", "jaiz", "ghunnah", "qalqalah", "tafkheem", "silent"]
ReadingValue = int | str


class ReadingChoice(BaseModel):
    """One allowed value of a reading setting."""

    value: ReadingValue
    label_ar: str


class ReadingSetting(BaseModel):
    """A reading setting the reciter may change (the rules table decides the choices)."""

    name: str
    label_ar: str
    choices: list[ReadingChoice]
    default: ReadingValue
    main: bool = Field(description="Shown first; the rest go under 'more reading choices'.")


class SurahInfo(BaseModel):
    index: int
    name: str
    ayat: int


class Limits(BaseModel):
    max_recording_seconds: int
    soft_recording_seconds: int = Field(description="Past this the result carries a warning.")
    max_upload_bytes: int
    max_ayat_manual: int = Field(description="Most ayat a reciter may choose in manual mode.")


class EngineInfo(BaseModel):
    quran_transcript: str
    rules: str


class Meta(BaseModel):
    """Everything the app needs before the first request: settings, surahs, limits."""

    reading: list[ReadingSetting]
    practices: dict[str, bool] = Field(description="Optional practices, off by default (raum).")
    surahs: list[SurahInfo]
    limits: Limits
    tajweed_classes: list[TajweedClass]
    engine: EngineInfo


class ReferenceRequest(BaseModel):
    """Whole ayat `aya_start`..`aya_end` of `sura`, with openings and reading settings."""

    sura: int = Field(ge=1, le=114)
    aya_start: int = Field(ge=1)
    aya_end: int = Field(ge=1)
    prefixes: list[Opening] = Field(default_factory=list)
    reading: dict[str, ReadingValue] = Field(
        default_factory=dict, description="Reading settings by name; unknown names are ignored."
    )


class ReferenceWord(BaseModel):
    """A word, its place in the Quran and its character span in `uthmani` (end exclusive)."""

    sura: int
    aya: int
    word: int = Field(description="Index within the ayah's words; matches the reciter timings.")
    start: int
    end: int
    ayah_last: bool


class ReferenceSegment(BaseModel):
    """A stretch read without stopping, or an opening (no words)."""

    kind: Literal["istiaatha", "basmala", "recitation"]
    start: int
    end: int
    words: list[ReferenceWord]


class Reference(BaseModel):
    """The text to show, with tajweed colours. Positions index into `uthmani`."""

    uthmani: str
    segments: list[ReferenceSegment]
    tajweed: list[tuple[int, int, TajweedClass]] = Field(description="[start, end, class] spans.")
    classes_present: list[TajweedClass]
