"""An analysis request's fields and its result (the worker's, and later the API's)."""

import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AnalysisQuery(BaseModel):
    """What to analyse, sent as query fields; the recording itself is the request body.

    Manual mode needs the text (sura, aya_start, aya_end). In auto mode the text is detected;
    sura and aya_end, when given, are a hint (the text recited last, to prefer reading in order).
    """

    mode: Literal["manual", "auto"] = "manual"
    sura: int | None = Field(default=None, ge=1, le=114)
    aya_start: int | None = Field(default=None, ge=1)
    aya_end: int | None = Field(default=None, ge=1)
    istiaatha: bool = False
    basmala: bool = False
    raum: bool = Field(default=False, description="Raum practice on («أتدرّب على الوقف بالرَّوم»).")
    reading: str = Field(default="{}", description="Reading settings as a JSON object, by name.")

    @field_validator("reading")
    @classmethod
    def _reading_is_a_json_object(cls, v: str) -> str:
        try:
            parsed = json.loads(v or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("reading must be a JSON object") from exc
        if not isinstance(parsed, dict):
            raise ValueError("reading must be a JSON object")
        return v or "{}"

    def reading_settings(self) -> dict[str, Any]:
        settings: dict[str, Any] = json.loads(self.reading)
        return settings


class TextUsed(BaseModel):
    sura: int
    aya_start: int
    aya_end: int
    prefixes: list[str]


class AnalysisWarning(BaseModel):
    code: Literal["cut_in_speech", "over_30s"]
    edges: list[Literal["start", "end"]]
    message_ar: str


class WordTime(BaseModel):
    """A recited word's span in the user's recording (one entry per recital)."""

    segment: int
    word: int
    sura: int
    aya: int
    start_s: float
    end_s: float


class Summary(BaseModel):
    mistakes: int = Field(description="Counted mistakes (never uncertain places or variants).")
    uncertain: int
    exact_match: bool


class EngineVersions(BaseModel):
    model_revision: str
    segmenter_revision: str
    quran_transcript: str
    rules: str


class AnalysisResult(BaseModel):
    """The result of one recording (docs/contracts/api.md, docs/model-and-analysis.md §4)."""

    mode: Literal["manual", "auto"]
    text: TextUsed
    duration_s: float
    summary: Summary
    detection: dict[str, Any] | None
    path: dict[str, Any] | None
    warnings: list[AnalysisWarning]
    word_times: list[WordTime]
    report: dict[str, Any]
    engine: EngineVersions
    timings_ms: dict[str, int]


class AnalysisRequest(AnalysisQuery):
    """The API's query for POST /v1/analyses: the worker's fields plus the app's id for this
    attempt. A resend with the same client_id returns the first result (kept 24 h)."""

    client_id: uuid.UUID = Field(description="A new UUID per attempt; reuse it to resend.")

    def worker_params(self) -> dict[str, Any]:
        """What the worker gets: everything but client_id, without empty fields."""
        return {k: v for k, v in self.model_dump(exclude={"client_id"}).items() if v is not None}


class AnalysisPending(BaseModel):
    """GET /v1/analyses/{client_id} while it is still being analysed (202)."""

    status: Literal["running"] = "running"


class WarmupState(BaseModel):
    """POST /v1/warmup: "warm" (200) when the worker answered moments ago, so nothing was sent;
    "warming" (202) when it is being woken."""

    state: Literal["warm", "warming"]
