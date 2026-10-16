"""Warm-up: wake the analysis worker while the user records."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import ClientDep, SessionDep, SettingsDep, WorkerDep
from app.contracts.analysis import WarmupState
from app.services.warmup_service import WarmupService

router = APIRouter(prefix="/v1", tags=["analyses"])


def warmup_service(session: SessionDep, settings: SettingsDep, worker: WorkerDep) -> WarmupService:
    return WarmupService(session, settings, worker)


ServiceDep = Annotated[WarmupService, Depends(warmup_service)]


@router.post(
    "/warmup",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=WarmupState,
    responses={status.HTTP_200_OK: {"model": WarmupState, "description": "Already warm"}},
)
async def post_warmup(client: ClientDep, service: ServiceDep, response: Response) -> WarmupState:
    """Call when the Record screen opens. 200 "warm": it answered moments ago, nothing sent.
    202 "warming": it is being woken in the background. Answers at once either way."""
    state = await service.warm(client)
    if state.state == "warm":
        response.status_code = status.HTTP_200_OK
    return state
