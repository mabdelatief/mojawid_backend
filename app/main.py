"""The API application factory and lifespan."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.adapters.worker_client import WorkerClient
from app.api.router import api_router
from app.config import Settings, get_settings
from app.db.session import dispose_engine, get_session_maker
from app.errors import register_exception_handlers
from app.log_config import configure_logging
from app.request_context import RequestIdMiddleware
from app.services.maintenance_service import purge_forever
from app.services.text_service import warm_up

logger = logging.getLogger("mojawid.main")


def _operation_id(route: APIRoute) -> str:
    """The handler's name as the OpenAPI operationId, for stable client method names."""
    return route.name


def build_lifespan(settings: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Start shared resources on boot, release them on shutdown."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        logger.info("Mojawid API starting", extra={"environment": settings.environment})
        await asyncio.to_thread(warm_up)  # the Quran and its special places, before traffic
        app.state.worker = WorkerClient.from_settings(settings)
        purge = asyncio.create_task(purge_forever(get_session_maker(settings), settings))
        try:
            yield
        finally:
            purge.cancel()
            await app.state.worker.close()
            await dispose_engine()
            logger.info("Mojawid API stopped")

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API."""
    resolved = settings or get_settings()
    configure_logging(resolved)
    docs = resolved.docs_enabled and resolved.environment != "production"
    app = FastAPI(
        title=resolved.app_name,
        version=resolved.app_version,
        lifespan=build_lifespan(resolved),
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
        generate_unique_id_function=_operation_id,
    )
    app.add_middleware(RequestIdMiddleware, header_name=resolved.request_id_header)
    # The web build calls the API from the browser; it must be allowed to send the access headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_origins),
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "X-Api-Key", "X-Install-Id", resolved.request_id_header],
        expose_headers=[resolved.request_id_header, "Retry-After"],
    )
    register_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
