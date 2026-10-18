"""Recording rows (app/db/models/recording.py). Never commits: the service owns the transaction."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import DONE, FAILED, RUNNING
from app.db.models.recording import Recording
from app.db.models.report import Report

# A recording with its report (at most one, by the report table's unique key), or None.
WithReport = tuple[Recording, Report | None]


class RecordingRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, values: dict[str, Any]) -> bool:
        """Insert a running row; False when this (install, client_id) is already kept."""
        stmt = (
            insert(Recording)
            .values(status=RUNNING, **values)
            .on_conflict_do_nothing(index_elements=[Recording.install_hash, Recording.client_id])
            .returning(Recording.id)
        )
        return (await self.session.scalar(stmt)) is not None

    async def id_for(self, install_hash: str, client_id: uuid.UUID) -> uuid.UUID | None:
        stmt = select(Recording.id).where(
            Recording.install_hash == install_hash, Recording.client_id == client_id
        )
        found: uuid.UUID | None = await self.session.scalar(stmt)
        return found

    async def get(self, recording_id: uuid.UUID) -> Recording | None:
        found: Recording | None = await self.session.get(Recording, recording_id)
        return found

    async def get_with_report(self, recording_id: uuid.UUID) -> WithReport | None:
        stmt = self._with_report().where(Recording.id == recording_id)
        row = (await self.session.execute(stmt)).first()
        return (row[0], row[1]) if row is not None else None

    @staticmethod
    def _with_report() -> Any:
        return select(Recording, Report).outerjoin(Report, Report.recording_id == Recording.id)

    async def finish(self, recording_id: uuid.UUID, result: dict[str, Any]) -> None:
        await self._set(recording_id, status=DONE, result=result, error_code=None)

    async def fail(self, recording_id: uuid.UUID, code: str, message: str) -> None:
        await self._set(recording_id, status=FAILED, error_code=code, error_message=message)

    async def _set(self, recording_id: uuid.UUID, **values: Any) -> None:
        stmt = (
            update(Recording)
            .where(Recording.id == recording_id)
            .values(updated_at=func.now(), **values)
        )
        await self.session.execute(stmt)

    async def page(self, before: tuple[datetime, uuid.UUID] | None, limit: int) -> list[WithReport]:
        """Newest first; `before` is the (created_at, id) of the last row of the previous page."""
        stmt = self._with_report().order_by(Recording.created_at.desc(), Recording.id.desc())
        if before is not None:
            stmt = stmt.where(tuple_(Recording.created_at, Recording.id) < before)
        rows = (await self.session.execute(stmt.limit(limit))).all()
        return [(r[0], r[1]) for r in rows]

    async def remove(self, recording_id: uuid.UUID) -> str | None:
        """Delete the row; returns its file name, or None when there was no such row."""
        stmt = delete(Recording).where(Recording.id == recording_id).returning(Recording.file_name)
        name: str | None = await self.session.scalar(stmt)
        return name
