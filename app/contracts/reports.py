"""Bad-result reports (docs/contracts/api.md, "Reports")."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ReportCategory = Literal["false_mistake", "missed_mistake", "wrong_ayat", "other"]


class ReportWord(BaseModel):
    """The word the user points at, indexed within its ayah as everywhere else."""

    sura: int = Field(ge=1, le=114)
    aya: int = Field(ge=1)
    word: int = Field(ge=0)


class ReportCreate(BaseModel):
    """POST /v1/reports. Only with the user's explicit agreement (`consent: true`)."""

    consent: bool = Field(description="The user ticked the consent box; must be true.")
    category: ReportCategory | None = Field(
        default=None,
        description="false_mistake «أشار إلى خطأ لم أقع فيه», missed_mistake «لم يلاحظ خطأً "
        "وقعت فيه», wrong_ayat «تعرّف على آيات غير التي قرأتها», other «شيء آخر».",
    )
    word: ReportWord | None = None
    note: str | None = Field(default=None, max_length=1000)
    analysis_client_id: uuid.UUID | None = Field(
        default=None, description="The client_id of the analysis reported, when there is one."
    )
    result: dict[str, Any] = Field(description="The result the user was shown, as received.")
    reading: dict[str, Any] = Field(default_factory=dict, description="The reading settings.")
    app_version: str | None = Field(default=None, max_length=40)


class ReportCreated(BaseModel):
    id: uuid.UUID
    upload_audio_until: datetime = Field(
        description="Send the recording with PUT /v1/reports/{id}/audio before this time."
    )
