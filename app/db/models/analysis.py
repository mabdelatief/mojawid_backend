"""Analyses, kept for a day so a resend never runs twice (idempotency on install + client_id).

A row holds the result the app was sent (or the error), never the recording. The install is
stored only as its HMAC. Rows older than `analysis_result_ttl_hours` are purged hourly.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RUNNING, DONE, FAILED = "running", "done", "failed"


class Analysis(Base):
    """One attempt, by the install that sent it and the app's id for the attempt."""

    __tablename__ = "analysis"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'done', 'failed')", name="status"),
        Index("ix_analysis_created_at", "created_at"),
    )

    install_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    status: Mapped[str] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    error_status: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
