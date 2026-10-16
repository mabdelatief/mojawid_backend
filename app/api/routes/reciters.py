"""Reciters and their word timings. Responses change only when the timings are re-imported, so
clients may cache them."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, SettingsDep, require_client
from app.contracts.reciters import ReciterList, ReciterTimings
from app.services.reciter_service import ReciterService

router = APIRouter(prefix="/v1/reciters", tags=["reciters"], dependencies=[Depends(require_client)])

_CACHE = "public, max-age=3600"


def reciter_service(session: SessionDep, settings: SettingsDep) -> ReciterService:
    return ReciterService(session, settings)


ServiceDep = Annotated[ReciterService, Depends(reciter_service)]


class TimingsQuery(BaseModel):
    """Which ayat: `from`..`to` of `surah`."""

    surah: int = Field(ge=1, le=114)
    first: int = Field(alias="from", ge=1)
    last: int = Field(alias="to", ge=1)


@router.get("", response_model=ReciterList)
async def list_reciters(response: Response, service: ServiceDep) -> ReciterList:
    """The reciters offered (all with word-by-word timings) and the default one."""
    response.headers["Cache-Control"] = _CACHE
    return await service.list_offered()


@router.get("/{slug}/timings", response_model=ReciterTimings)
async def reciter_timings(
    slug: str,
    query: Annotated[TimingsQuery, Query()],
    response: Response,
    service: ServiceDep,
) -> ReciterTimings:
    """Word timings and audio URLs for ayat `from`..`to` of `surah` (at most 20)."""
    response.headers["Cache-Control"] = _CACHE
    return await service.timings(slug, query.surah, query.first, query.last)
