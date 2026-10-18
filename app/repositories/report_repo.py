"""Report rows. Never commits: the service owns the transaction."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.report import Report


class ReportRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, report: Report) -> None:
        self.session.add(report)

    async def get(self, report_id: uuid.UUID) -> Report | None:
        found: Report | None = await self.session.get(Report, report_id)
        return found

    async def newest(self, limit: int) -> Sequence[Report]:
        stmt = select(Report).order_by(Report.created_at.desc()).limit(limit)
        return (await self.session.scalars(stmt)).all()

    async def set_audio(self, report_id: uuid.UUID, key: str, content_type: str, size: int) -> None:
        stmt = (
            update(Report)
            .where(Report.id == report_id)
            .values(
                audio_key=key,
                audio_content_type=content_type,
                audio_size=size,
                audio_uploaded_at=func.now(),
            )
        )
        await self.session.execute(stmt)

    async def mark_reviewed(self, report_id: uuid.UUID) -> None:
        """Reviewed, with its audio gone."""
        stmt = (
            update(Report)
            .where(Report.id == report_id)
            .values(reviewed_at=func.now(), audio_key=None)
        )
        await self.session.execute(stmt)

    async def delete(self, report_id: uuid.UUID) -> None:
        await self.session.execute(delete(Report).where(Report.id == report_id))

    async def delete_stale(self, no_audio_before: datetime, reviewed_before: datetime) -> int:
        """Reports whose audio never came within the window, and reports reviewed long ago. A
        report on a kept recording has no upload and stays, so the recording stays reported."""
        never_sent = (Report.audio_uploaded_at.is_(None)) & (Report.created_at < no_audio_before)
        old_review = Report.reviewed_at < reviewed_before
        stmt = (
            delete(Report)
            .where(Report.recording_id.is_(None), never_sent | old_review)
            .returning(Report.id)
        )
        return len((await self.session.execute(stmt)).all())
