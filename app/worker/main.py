"""The worker app: POST /v1/analyze (the recording as the raw body), POST /v1/warm, GET /healthz.

The models load in the lifespan, so the port only answers once they're ready (on Modal that is
what a cold start waits for). Only the API calls the worker, with the worker token. Errors use
the same envelope and codes as the API; a recording never reaches a log or an error message.

    .venv/bin/uvicorn app.worker.main:app --port 8200      # dev, on this laptop's GPU
"""

import asyncio
import hmac
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.api.body import read_capped_body
from app.config import get_settings
from app.contracts.analysis import AnalysisQuery, AnalysisResult
from app.engine.pipeline import detect
from app.engine.pipeline.errors import AnalysisError
from app.errors import AppError, register_exception_handlers
from app.log_config import configure_logging
from app.request_context import RequestIdMiddleware
from app.services.text_service import warm_up as warm_text
from app.worker.service import Runner, WorkerService
from app.worker.settings import WorkerSettings, get_worker_settings

log = logging.getLogger("mojawid.worker")

# 400: the request itself is wrong; 422: the recording can't give a result.
_REQUEST_ERRORS = {"invalid_reading_settings", "invalid_text_selection"}


class Ready(BaseModel):
    ready: bool
    device: str


def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    """`Authorization: Bearer <MOJAWID_WORKER_TOKEN>`, compared in constant time."""
    expected = f"Bearer {get_worker_settings().token}".encode()
    if not hmac.compare_digest((authorization or "").encode(), expected):
        raise AppError("invalid_worker_token", "Not allowed.", status.HTTP_401_UNAUTHORIZED)


TokenDep = Annotated[None, Depends(require_token)]


def _load_gpu_runner(settings: WorkerSettings) -> Runner:
    from app.engine.pipeline.models.gpu import load_runner  # torch only when really serving

    return load_runner(settings.device)


def create_worker_app(
    load_runner: Callable[[WorkerSettings], Runner] = _load_gpu_runner,
) -> FastAPI:
    """The worker; tests pass a fake runner loader."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = get_worker_settings()
        runner = await asyncio.to_thread(load_runner, settings)
        await asyncio.to_thread(warm_text)
        await asyncio.to_thread(detect.warm_up)
        app.state.service = WorkerService(runner)
        app.state.device = str(getattr(runner, "device", "cpu"))
        log.info("worker ready", extra={"device": app.state.device})
        yield

    configure_logging(get_settings())
    app = FastAPI(
        title="Mojawid worker", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_middleware(RequestIdMiddleware, header_name="X-Request-ID")
    register_exception_handlers(app)

    @app.get("/healthz", response_model=Ready)
    async def healthz(request: Request) -> Ready:
        return Ready(
            ready=hasattr(request.app.state, "service"),
            device=getattr(request.app.state, "device", ""),
        )

    @app.post("/v1/warm", status_code=status.HTTP_200_OK, response_model=Ready)
    async def warm(request: Request, _: TokenDep) -> Ready:
        """Answering at all means the models are loaded (the lifespan finished)."""
        return Ready(ready=True, device=request.app.state.device)

    @app.post("/v1/analyze", status_code=status.HTTP_200_OK, response_model=AnalysisResult)
    async def analyze(
        request: Request, query: Annotated[AnalysisQuery, Query()], _: TokenDep
    ) -> AnalysisResult:
        """The result for the recording sent as the request body."""
        audio = await read_capped_body(request)
        service: WorkerService = request.app.state.service
        try:
            return await run_in_threadpool(service.analyse_upload, audio, query)
        except AnalysisError as exc:
            code = status.HTTP_400_BAD_REQUEST if exc.code in _REQUEST_ERRORS else 422
            raise AppError(exc.code, exc.message, code) from exc

    return app


app = create_worker_app()
