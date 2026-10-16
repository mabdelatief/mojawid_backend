"""Every route is mounted here, and only here (CLAUDE.md; enforced by the discipline scan)."""

from fastapi import APIRouter

from app.api.routes.analyses import router as analyses_router
from app.api.routes.health import router as health_router
from app.api.routes.reciters import router as reciters_router
from app.api.routes.text import router as text_router
from app.api.routes.warmup import router as warmup_router
from app.errors import ERROR_RESPONSES

api_router = APIRouter(responses=ERROR_RESPONSES)
api_router.include_router(health_router)
api_router.include_router(reciters_router)
api_router.include_router(text_router)
api_router.include_router(analyses_router)
api_router.include_router(warmup_router)
