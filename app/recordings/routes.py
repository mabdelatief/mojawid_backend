"""The kept recordings, for every tester: the list, one recording with its result, and its audio
(closed testing; docs/contracts/api.md, "Recordings")."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse

from app.api.deps import ClientDep, SessionDep, SettingsDep
from app.contracts.recordings import (
    RecordingDetail,
    RecordingPage,
    RecordingReportCreate,
    RecordingReportCreated,
)
from app.recordings.reporting import RecordingReporter
from app.recordings.service import MAX_PAGE, RecordingService

router = APIRouter(prefix="/v1/recordings", tags=["recordings"])


def recording_service(session: SessionDep, settings: SettingsDep) -> RecordingService:
    return RecordingService(session, settings)


ServiceDep = Annotated[RecordingService, Depends(recording_service)]


@router.get("", response_model=RecordingPage)
async def list_recordings(
    client: ClientDep,
    service: ServiceDep,
    before: Annotated[str | None, Query(description="`next_before` of the previous page.")] = None,
    limit: Annotated[int | None, Query(ge=1, le=MAX_PAGE)] = None,
) -> RecordingPage:
    """Every kept recording, newest first, from every tester."""
    return await service.page(before, limit)


@router.get("/{recording_id}", response_model=RecordingDetail)
async def get_recording(
    recording_id: uuid.UUID, client: ClientDep, service: ServiceDep
) -> RecordingDetail:
    """One recording with its full result (or its error)."""
    return await service.detail(recording_id)


@router.get(
    "/{recording_id}/audio",
    response_class=FileResponse,
    responses={200: {"content": {"audio/*": {}}, "description": "The recording as it was sent."}},
)
async def get_recording_audio(
    recording_id: uuid.UUID, client: ClientDep, service: ServiceDep
) -> FileResponse:
    """The audio exactly as it was uploaded, with its content type. Range requests work."""
    path, media_type = await service.audio(recording_id)
    return FileResponse(path, media_type=media_type)


def recording_reporter(session: SessionDep, settings: SettingsDep) -> RecordingReporter:
    return RecordingReporter(session, settings)


ReporterDep = Annotated[RecordingReporter, Depends(recording_reporter)]


@router.post(
    "/{recording_id}/report",
    status_code=status.HTTP_201_CREATED,
    response_model=RecordingReportCreated,
)
async def report_recording(
    recording_id: uuid.UUID, body: RecordingReportCreate, client: ClientDep, reporter: ReporterDep
) -> RecordingReportCreated:
    """Report this recording's result as wrong. Once per recording, by anyone: a second report
    gets 409 recording_already_reported, and every tester sees the first in `report`."""
    return await reporter.report(client, recording_id, body)
