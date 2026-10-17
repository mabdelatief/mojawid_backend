"""Every recording and its result, kept while Mojawid is in closed testing (CLAUDE.md, the user's
decision 2026-10-17). Any tester can list and play them.

The audio is a file in `recordings_dir` (app/recordings/store.py), named after the row. Who made
it: the install, as its HMAC, and the tester's Cloudflare Access email when the request came
through the web front. One row per (install, client_id), so a resend is never kept twice.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Recording(Base):
    __tablename__ = "recording"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'done', 'failed')", name="status"),
        UniqueConstraint("install_hash", "client_id"),
        Index("ix_recording_created_at", "created_at"),
        Index("ix_recording_tester_email", "tester_email"),
        Index("ix_recording_install_hash", "install_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    install_hash: Mapped[str] = mapped_column(Text)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tester_email: Mapped[str | None] = mapped_column(Text)
    request: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    file_name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
