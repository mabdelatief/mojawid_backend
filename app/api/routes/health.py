"""Liveness and readiness. No API key: these are for the host and the load balancer."""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import SessionDep, SettingsDep

router = APIRouter(tags=["health"])


class Health(BaseModel):
    """The process is up."""

    status: str
    version: str
    environment: str


class Ready(BaseModel):
    """The process can serve: the database answers."""

    status: str


@router.get("/healthz", response_model=Health)
async def healthz(settings: SettingsDep) -> Health:
    """Liveness: no dependencies touched."""
    return Health(status="ok", version=settings.app_version, environment=settings.environment)


@router.get("/readyz", response_model=Ready)
async def readyz(session: SessionDep) -> Ready:
    """Readiness: the database answers a trivial query."""
    await session.execute(text("SELECT 1"))
    return Ready(status="ready")
