"""Meta (settings, surahs, limits) and the reference text with tajweed colours."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import SettingsDep, require_client
from app.contracts.text import Meta, Reference, ReferenceRequest
from app.services.text_service import TextService

router = APIRouter(prefix="/v1", tags=["text"], dependencies=[Depends(require_client)])


def text_service(settings: SettingsDep) -> TextService:
    return TextService(settings)


ServiceDep = Annotated[TextService, Depends(text_service)]


@router.get("/meta", response_model=Meta)
async def get_meta(response: Response, service: ServiceDep) -> Meta:
    """Reading settings (choices, defaults, Arabic labels), surahs, limits, tajweed classes."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return service.meta()


@router.post("/reference", status_code=status.HTTP_200_OK, response_model=Reference)
async def post_reference(body: ReferenceRequest, service: ServiceDep) -> Reference:
    """The Uthmani text of whole ayat, its words and tajweed spans, under the reading settings.
    It is computed, not stored, hence POST with 200."""
    return await service.reference(body)
