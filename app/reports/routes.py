"""Bad-result reports from the app: the report, then its recording as the raw request body."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.api.body import read_capped_body
from app.api.deps import ClientDep, ObjectStoreDep, SessionDep, SettingsDep
from app.contracts.reports import ReportCreate, ReportCreated
from app.reports.service import ReportService

router = APIRouter(prefix="/v1/reports", tags=["reports"])


def report_service(
    session: SessionDep, settings: SettingsDep, store: ObjectStoreDep
) -> ReportService:
    return ReportService(session, settings, store)


ServiceDep = Annotated[ReportService, Depends(report_service)]


async def report_body(request: Request) -> ReportCreate:
    """The JSON body, read with the 2 MiB cap (it carries the result the user saw)."""
    raw = await read_capped_body(request)
    try:
        return ReportCreate.model_validate_json(raw)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ReportCreated,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": ReportCreate.model_json_schema()}},
        }
    },
)
async def post_report(
    body: Annotated[ReportCreate, Depends(report_body)], client: ClientDep, service: ServiceDep
) -> ReportCreated:
    """A bad-result report. Only with the user's explicit agreement (`consent: true`); send
    its recording next, with PUT /v1/reports/{id}/audio."""
    return await service.create(client, body)


@router.put("/{report_id}/audio", status_code=status.HTTP_204_NO_CONTENT)
async def put_report_audio(
    report_id: uuid.UUID, request: Request, client: ClientDep, service: ServiceDep
) -> Response:
    """The report's recording as the raw body (≤ 2 MiB): once, within an hour of the report."""
    audio = await read_capped_body(request)
    await service.upload_audio(client, report_id, audio, request.headers.get("content-type"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
