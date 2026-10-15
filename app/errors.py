"""AppError and the exception handlers that turn every failure into
`{"error": {"code", "message", "request_id", "details"}}`.

Codes are stable: the app shows its own Arabic text by code. Messages are short English for
developers. Nothing from the request is ever echoed back or logged: validation details carry
only the location, message and type, never the submitted value.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.request_context import get_request_id

logger = logging.getLogger("mojawid.errors")


class ErrorPayload(BaseModel):
    """The body of an error response."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    request_id: str | None = None
    details: Any | None = None


class ErrorResponse(BaseModel):
    """The error envelope."""

    model_config = ConfigDict(frozen=True)

    error: ErrorPayload


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse, "description": "Bad request"},
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "Invalid API key"},
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Not found"},
    422: {"model": ErrorResponse, "description": "Validation error"},
    status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse, "description": "Rate limited"},
}


class AppError(Exception):
    """An expected failure with a stable code and an HTTP status."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        self.headers = headers


def error_response(
    status_code: int, payload: ErrorPayload, headers: dict[str, str] | None = None
) -> JSONResponse:
    """A JSON error response stamped with the request id."""
    stamped = payload.model_copy(update={"request_id": get_request_id()})
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(ErrorResponse(error=stamped)),
        headers=headers,
    )


async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    """AppError → its code and status."""
    if not isinstance(exc, AppError):
        return await handle_unexpected(request, exc)
    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.warning("app error", extra={"error_code": exc.code, "path": request.url.path})
    payload = ErrorPayload(code=exc.code, message=exc.message, details=exc.details)
    return error_response(exc.status_code, payload, exc.headers)


async def handle_http_error(request: Request, exc: Exception) -> JSONResponse:
    """Starlette's own HTTP errors (unknown route, wrong method) in the same envelope."""
    if not isinstance(exc, StarletteHTTPException):
        return await handle_unexpected(request, exc)
    code = "not_found" if exc.status_code == status.HTTP_404_NOT_FOUND else "http_error"
    payload = ErrorPayload(code=code, message=str(exc.detail) if exc.detail else "HTTP error")
    return error_response(exc.status_code, payload)


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    """Request validation → 422 `invalid_request`, without echoing the submitted values."""
    if not isinstance(exc, RequestValidationError):
        return await handle_unexpected(request, exc)
    details = [{k: e.get(k) for k in ("loc", "msg", "type")} for e in exc.errors()]
    payload = ErrorPayload(code="invalid_request", message="Invalid request.", details=details)
    return error_response(422, payload)


async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    """Anything else → 500 with no internals. Logs the type only (a traceback in dev)."""
    logger.error(
        "unhandled error",
        extra={"error_type": type(exc).__name__, "path": request.url.path},
        exc_info=exc if get_settings().debug else None,
    )
    payload = ErrorPayload(code="internal_error", message="Internal server error.")
    return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, payload)


def register_exception_handlers(app: FastAPI) -> None:
    """Install the handlers. Each takes a plain Exception and narrows it, so no cast is needed."""
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected)
