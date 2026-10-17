"""Wire models for the kept recordings (closed testing; docs/contracts/api.md, "Recordings")."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.contracts.analysis import AnalysisResult, Summary


class RecordingText(BaseModel):
    """The text checked: the one detected in auto mode, else the one chosen; null fields when
    neither is known (an auto recording that failed)."""

    sura: int | None
    aya_start: int | None
    aya_end: int | None


class RecordingItem(BaseModel):
    """One kept recording, as listed."""

    id: uuid.UUID
    client_id: uuid.UUID = Field(description="The app's id for the attempt (POST /v1/analyses).")
    created_at: datetime
    tester: str | None = Field(
        description="Who recorded it: the part of the tester's login email before «@»; null for "
        "a phone build on the Wi-Fi, which has no login."
    )
    mode: Literal["manual", "auto"]
    text: RecordingText
    duration_s: float | None
    summary: Summary | None = Field(description="Null until analysed, or when it failed.")
    status: Literal["running", "done", "failed"]
    error_code: str | None


class RecordingPage(BaseModel):
    """Newest first. Pass `next_before` as `before` for the next page; null on the last one."""

    items: list[RecordingItem]
    next_before: str | None


class RecordingDetail(RecordingItem):
    """One recording with its full result, exactly as POST /v1/analyses returned it."""

    result: AnalysisResult | None
    error_message: str | None
