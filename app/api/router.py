"""Every route is mounted here, and only here (CLAUDE.md; enforced by the discipline scan)."""

from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.api.routes.reciters import router as reciters_router
from app.errors import ERROR_RESPONSES

api_router = APIRouter(responses=ERROR_RESPONSES)
api_router.include_router(health_router)
api_router.include_router(reciters_router)
