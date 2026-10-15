"""Reciters and their word timings (docs/recitations.md). Filled by tools/load_timings.py from
the output of tools/import_timings.py; read at runtime instead of any third-party API."""

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Integer,
    SmallInteger,
    Text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Recitation(Base):
    """One reciter's recording set. The ayah file is
    `bucket_prefix + file_pattern.format(surah=…, ayah=…)` in the verseaudiofiles bucket."""

    __tablename__ = "recitation"
    __table_args__ = (
        CheckConstraint("style IN ('murattal', 'mujawwad', 'muallim')", name="style"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name_ar: Mapped[str] = mapped_column(Text)
    name_en: Mapped[str] = mapped_column(Text)
    style: Mapped[str] = mapped_column(Text)
    bucket_prefix: Mapped[str] = mapped_column(Text)
    file_pattern: Mapped[str] = mapped_column(Text)
    timing_source: Mapped[str] = mapped_column(Text)
    offered: Mapped[bool] = mapped_column(Boolean, server_default=true())


class RecitationAyahTiming(Base):
    """One row per reciter and ayah. `segments` rows are [first_word, last_word, start_ms,
    end_ms]: word indexes 0-based and inclusive into the ayah's words (Tanzil Uthmani split on
    spaces), times into that ayah's mp3. A multi-word segment is a merged span; a word in no
    segment has no timing for this reciter."""

    __tablename__ = "recitation_ayah_timing"
    __table_args__ = (
        CheckConstraint("surah BETWEEN 1 AND 114", name="surah"),
        CheckConstraint("ayah >= 1", name="ayah"),
        CheckConstraint("array_ndims(segments) = 2 OR segments = '{}'", name="segments_2d"),
    )

    recitation_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("recitation.id", ondelete="CASCADE"), primary_key=True
    )
    surah: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    ayah: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    segments: Mapped[list[list[int]]] = mapped_column(ARRAY(Integer, dimensions=2))
