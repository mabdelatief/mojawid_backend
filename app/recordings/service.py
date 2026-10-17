"""Listing, reading, playing and deleting the kept recordings (closed testing).

Every tester sees every recording. Who made it is shown as the part of the login email before
«@»; the full email and the install stay in the database for a later "own recordings only".
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import anyio.to_thread
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.contracts.analysis import AnalysisResult
from app.contracts.recordings import RecordingDetail, RecordingItem, RecordingPage, RecordingText
from app.db.models.recording import Recording
from app.errors import AppError
from app.recordings.keeper import store_for
from app.repositories.recording_repo import RecordingRepo

MAX_PAGE = 100


def not_found() -> AppError:
    return AppError("recording_not_found", "No such recording.", status.HTTP_404_NOT_FOUND)


def cursor_of(row: Recording) -> str:
    return f"{row.created_at.isoformat()}_{row.id}"


def parse_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        when, rid = cursor.rsplit("_", 1)
        return datetime.fromisoformat(when), uuid.UUID(rid)
    except ValueError as exc:
        raise AppError("invalid_cursor", "That page cursor isn't valid.") from exc


def _text(row: Recording) -> RecordingText:
    used: dict[str, Any] = (row.result or {}).get("text") or row.request
    return RecordingText(
        sura=used.get("sura"), aya_start=used.get("aya_start"), aya_end=used.get("aya_end")
    )


def item_of(row: Recording) -> RecordingItem:
    result = row.result or {}
    return RecordingItem.model_validate({
        "id": row.id,
        "client_id": row.client_id,
        "created_at": row.created_at,
        "tester": row.tester_email.split("@")[0] if row.tester_email else None,
        "mode": row.request.get("mode", "manual"),
        "text": _text(row),
        "duration_s": result.get("duration_s"),
        "summary": result.get("summary"),
        "status": row.status,
        "error_code": row.error_code,
    })  # fmt: skip


class RecordingService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repo = RecordingRepo(session)
        self.store = store_for(settings)

    async def page(self, before: str | None, limit: int | None) -> RecordingPage:
        size = min(limit or self.settings.recordings_page_size, MAX_PAGE)
        rows = await self.repo.page(parse_cursor(before) if before else None, size + 1)
        more = len(rows) > size
        rows = rows[:size]
        return RecordingPage(
            items=[item_of(r) for r in rows], next_before=cursor_of(rows[-1]) if more else None
        )

    async def detail(self, recording_id: uuid.UUID) -> RecordingDetail:
        row = await self._row(recording_id)
        result = AnalysisResult.model_validate(row.result) if row.result else None
        return RecordingDetail(
            **item_of(row).model_dump(), result=result, error_message=row.error_message
        )

    async def audio(self, recording_id: uuid.UUID) -> tuple[Path, str]:
        """The file and its content type; 404 when the row or the file is gone."""
        row = await self._row(recording_id)
        path = self.store.path(row.file_name)
        if not await anyio.to_thread.run_sync(path.is_file):
            raise not_found()
        return path, row.content_type

    async def delete(self, recording_id: uuid.UUID) -> None:
        """The row, then the file (admin page)."""
        name = await self.repo.remove(recording_id)
        if name is None:
            raise not_found()
        await self.session.commit()
        await anyio.to_thread.run_sync(self.store.delete, name)

    async def recent(self, limit: int) -> list[Recording]:
        return await self.repo.page(None, limit)

    async def _row(self, recording_id: uuid.UUID) -> Recording:
        row = await self.repo.get(recording_id)
        if row is None:
            raise not_found()
        return row
