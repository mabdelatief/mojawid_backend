"""Wire models for the kept recordings (closed testing; docs/contracts/api.md, "Recordings")."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.contracts.analysis import AnalysisResult, Summary
from app.contracts.reports import ReportCategory, ReportWord


class RecordingText(BaseModel):
    """The text checked: the one detected in auto mode, else the one chosen; null fields when
    neither is known (an auto recording that failed)."""

    sura: int | None
    aya_start: int | None
    aya_end: int | None


class RecordingReport(BaseModel):
    """The one report on this recording's result: shown to every tester in place of the button."""

    created_at: datetime
    reporter: str | None = Field(
        description="The part of the reporter's login email before «@»; null for a phone build."
    )
    category: ReportCategory | None
    note: str | None


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
    report: RecordingReport | None = Field(
        description="Set once the result was reported as wrong; it can't be reported again."
    )


class RecordingPage(BaseModel):
    """Newest first. Pass `next_before` as `before` for the next page; null on the last one."""

    items: list[RecordingItem]
    next_before: str | None


class RecordingDetail(RecordingItem):
    """One recording with its full result, exactly as POST /v1/analyses returned it."""

    result: AnalysisResult | None
    error_message: str | None


class RecordingReportCreate(BaseModel):
    """POST /v1/recordings/{id}/report: this recording's result is wrong. No consent or upload is
    needed: the recording is already kept."""

    category: ReportCategory | None = Field(
        default=None,
        description="false_mistake «أشار إلى خطأ لم يُرتكب», missed_mistake «لم يلاحظ خطأً», "
        "wrong_ayat «تعرّف على آيات غير المقروءة», other «شيء آخر».",
    )
    word: ReportWord | None = None
    note: str | None = Field(default=None, max_length=1000)
    app_version: str | None = Field(default=None, max_length=40)


class RecordingReportCreated(BaseModel):
    id: uuid.UUID
    report: RecordingReport
