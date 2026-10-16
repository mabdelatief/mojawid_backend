"""Warm-up: wake the analysis worker while the user records."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import ClientDep, SessionDep, SettingsDep, WorkerDep
from app.contracts.analysis import WarmupAccepted
from app.services.warmup_service import WarmupService

router = APIRouter(prefix="/v1", tags=["analyses"])


def warmup_service(session: SessionDep, settings: SettingsDep, worker: WorkerDep) -> WarmupService:
    return WarmupService(session, settings, worker)


ServiceDep = Annotated[WarmupService, Depends(warmup_service)]


@router.post("/warmup", status_code=status.HTTP_202_ACCEPTED, response_model=WarmupAccepted)
async def post_warmup(client: ClientDep, service: ServiceDep) -> WarmupAccepted:
    """Call when the Record screen opens. Answers at once; the worker starts in the background."""
    return await service.warm(client)
