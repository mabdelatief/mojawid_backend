"""Logging: console in dev, one JSON object per line in production, every record stamped with
the request id. Log calls must never pass audio, uploads or request bodies (CLAUDE.md; the
discipline scan checks the obvious cases)."""

import json
import logging
from typing import Any

from app.config import Settings
from app.request_context import get_request_id

_RESERVED = set(logging.makeLogRecord({}).__dict__)


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, including structured `extra=` fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    """Install the root handler for the configured format and level."""
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        fmt = "%(asctime)s %(levelname)-8s %(name)s [req=%(request_id)s] %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    # Request lines carry query strings (an analysis' reading settings): never logged.
    for name in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
