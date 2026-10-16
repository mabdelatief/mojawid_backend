"""Rate-limit counters: one row per (key, fixed window). Keys hold only HMACs of install ids
and IPs. Rows for windows that have ended are purged by the maintenance job (phase 6)."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RateLimitCounter(Base):
    """How many requests `key` made in the window starting at `window_start`."""

    __tablename__ = "rate_limit_counter"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
