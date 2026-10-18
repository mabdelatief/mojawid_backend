"""Bad-result reports, sent only with the user's explicit consent.

The report's audio sits in the private bucket under `audio_key` until the report is marked
reviewed, when it's deleted at once; the row goes `report_keep_after_review_days` later. A report
whose audio never followed within the upload window is purged. The install is kept only as its
HMAC.

A report on a kept recording (closed testing, `recording_id` set) needs none of that: its audio is
the kept recording, so nothing is uploaded, «reviewed» leaves the recording alone, and the row
isn't purged. There is at most one per recording (the unique key), which is how the app knows a
recording was already reported.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CATEGORIES = ("false_mistake", "missed_mistake", "wrong_ayat", "other")


class Report(Base):
    __tablename__ = "report"
    __table_args__ = (
        CheckConstraint(
            "category IS NULL OR category IN ('false_mistake', 'missed_mistake', 'wrong_ayat', "
            "'other')",
            name="category",
        ),
        Index("ix_report_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    install_hash: Mapped[str] = mapped_column(Text)
    platform: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    word: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    note: Mapped[str | None] = mapped_column(Text)
    analysis_client_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reading: Mapped[dict[str, Any]] = mapped_column(JSONB)
    app_version: Mapped[str | None] = mapped_column(Text)
    audio_key: Mapped[str | None] = mapped_column(Text)
    audio_content_type: Mapped[str | None] = mapped_column(Text)
    audio_size: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    audio_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recording_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("recording.id", ondelete="CASCADE"), unique=True
    )
    reporter_email: Mapped[str | None] = mapped_column(Text)
