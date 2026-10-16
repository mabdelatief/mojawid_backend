"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.client import Client, identify
from app.adapters.worker_client import WorkerClient
from app.config import Settings, get_settings
from app.db.session import get_db_session

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def require_client(
    request: Request,
    settings: SettingsDep,
    x_api_key: Annotated[str | None, Header()] = None,
    x_install_id: Annotated[str | None, Header()] = None,
) -> Client:
    """Every /v1 route: a valid app key and install id. Raises invalid_api_key /
    missing_install_id / invalid_install_id."""
    peer = request.client.host if request.client else None
    return identify(settings, x_api_key, x_install_id, peer, dict(request.headers))


ClientDep = Annotated[Client, Depends(require_client)]


def get_worker(request: Request) -> WorkerClient:
    """The worker client the lifespan created (tests override this)."""
    worker: WorkerClient = request.app.state.worker
    return worker


WorkerDep = Annotated[WorkerClient, Depends(get_worker)]
