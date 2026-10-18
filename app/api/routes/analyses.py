"""Analyses: the recording as the raw request body (never a form upload: Starlette writes those to
disk), the request's fields in the query. Idempotent on client_id for a day. During closed testing
the recording is kept (app/recordings/), and its id comes back in `X-Recording-Id`."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.body import read_capped_body
from app.api.deps import ClientDep, SessionDep, SettingsDep, WorkerDep
from app.contracts.analysis import AnalysisPending, AnalysisRequest, AnalysisResult
from app.services.analysis_service import AnalysisService, Upload

router = APIRouter(prefix="/v1/analyses", tags=["analyses"])


def analysis_service(
    session: SessionDep, settings: SettingsDep, worker: WorkerDep
) -> AnalysisService:
    return AnalysisService(session, settings, worker)


ServiceDep = Annotated[AnalysisService, Depends(analysis_service)]


@router.post(
    "",
    status_code=status.HTTP_200_OK,
    response_model=AnalysisResult,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"audio/*": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def post_analysis(
    request: Request,
    response: Response,
    query: Annotated[AnalysisRequest, Query()],
    client: ClientDep,
    service: ServiceDep,
) -> AnalysisResult:
    """Analyse the recording sent as the body (≤ 2 MiB, any common format). Resending with the
    same client_id returns the first result; it is computed once, hence POST with 200. The kept
    recording's id is in the `X-Recording-Id` header."""
    upload = Upload(await read_capped_body(request), request.headers.get("content-type"))
    done = await service.analyse(client, query, upload)
    if done.recording_id is not None:
        response.headers["X-Recording-Id"] = str(done.recording_id)
    return done.result


@router.get(
    "/{client_id}",
    response_model=AnalysisResult,
    responses={status.HTTP_202_ACCEPTED: {"model": AnalysisPending}},
)
async def get_analysis(
    client_id: uuid.UUID, client: ClientDep, service: ServiceDep, response: Response
) -> AnalysisResult | JSONResponse:
    """The result (200), still running (202), the analysis' own error, or 404. Ask this after a
    timeout, before sending the recording again. A 200 carries `X-Recording-Id`, as POST does."""
    found = await service.result(client, client_id)
    if isinstance(found, AnalysisPending):
        return JSONResponse(found.model_dump(), status_code=status.HTTP_202_ACCEPTED)
    if found.recording_id is not None:
        response.headers["X-Recording-Id"] = str(found.recording_id)
    return found.result
