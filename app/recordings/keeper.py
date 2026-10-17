"""Keeping each analysed recording and its outcome (AnalysisService calls this).

The file is written before its row, so a row always has its file. A resend of a recording that
is already kept (same install and client_id) writes nothing: the extra file is removed again and
the first recording's id is returned. Commits are the caller's.
"""

import uuid
from pathlib import Path
from typing import Any

import anyio.to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.client import Client
from app.config import Settings
from app.contracts.analysis import AnalysisRequest
from app.recordings.store import RecordingStore, file_name_for, media_type
from app.repositories.recording_repo import RecordingRepo


def store_for(settings: Settings) -> RecordingStore:
    return RecordingStore(Path(settings.recordings_dir).expanduser())


class RecordingKeeper:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.repo = RecordingRepo(session)
        self.store = store_for(settings)

    async def keep(
        self, client: Client, request: AnalysisRequest, audio: bytes, content_type: str | None
    ) -> uuid.UUID:
        """The recording's id, saving the audio and a running row unless it is already kept."""
        rid, kind = uuid.uuid4(), media_type(content_type)
        name = file_name_for(rid, kind)
        await anyio.to_thread.run_sync(self.store.save, name, audio)
        added = await self.repo.add({
            "id": rid,
            "install_hash": client.install_hash,
            "client_id": request.client_id,
            "tester_email": client.tester_email,
            "request": request.model_dump(mode="json", exclude={"client_id"}),
            "content_type": kind,
            "size_bytes": len(audio),
            "file_name": name,
        })  # fmt: skip
        if added:
            return rid
        await anyio.to_thread.run_sync(self.store.delete, name)
        existing = await self.id_for(client, request.client_id)
        return existing if existing is not None else rid

    async def id_for(self, client: Client, client_id: uuid.UUID) -> uuid.UUID | None:
        return await self.repo.id_for(client.install_hash, client_id)

    async def finished(self, rid: uuid.UUID, result: dict[str, Any]) -> None:
        await self.repo.finish(rid, result)

    async def failed(self, rid: uuid.UUID, code: str, message: str) -> None:
        await self.repo.fail(rid, code, message)
