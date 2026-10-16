"""The API's client for the analysis worker (app/worker/main.py): dev on this laptop's GPU,
production on a Modal Server.

- One `httpx.AsyncClient`, created in the lifespan, with the worker token.
- The recording goes as the raw request body, from memory; nothing of it is logged.
- While the worker starts (connection refused, 502/503/504) the call is retried with backoff, up
  to `worker_retry_window_s` (a Modal cold start takes 15–40 s).
- Never retried after a read timeout: the worker may already be analysing it.
- The worker's own errors (same envelope and codes as the API) pass through unchanged.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx
from fastapi import status

from app.config import Settings
from app.errors import AppError

logger = logging.getLogger("mojawid.worker_client")

RETRY_STATUSES = {502, 503, 504}
PASS_THROUGH = {400, 413, 422}
BACKOFF_S = (0.5, 1.0, 2.0, 4.0, 5.0)  # then 5 s until the window ends

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


def unavailable() -> AppError:
    return AppError(
        "analysis_unavailable",
        "The analysis service is unavailable; try again shortly.",
        status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def timed_out() -> AppError:
    return AppError(
        "analysis_timeout",
        "The analysis took too long; ask for the result before sending it again.",
        status.HTTP_504_GATEWAY_TIMEOUT,
    )


def _worker_error(response: httpx.Response) -> AppError:
    """The worker's own error, unchanged (its envelope and codes are the API's)."""
    try:
        error = response.json()["error"]
        return AppError(str(error["code"]), str(error["message"]), response.status_code)
    except (ValueError, KeyError, TypeError):
        return unavailable()


class WorkerClient:
    """POST /v1/analyze and /v1/warm on the worker."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        retry_window_s: float,
        sleep: Sleep = asyncio.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        self.http = http
        self.retry_window_s = retry_window_s
        self.sleep = sleep
        self.clock = clock
        self.last_answered: float | None = None  # clock() of the worker's last real answer

    @classmethod
    def from_settings(cls, settings: Settings) -> "WorkerClient":
        timeout = httpx.Timeout(
            settings.worker_read_timeout_s, connect=settings.worker_connect_timeout_s
        )
        http = httpx.AsyncClient(
            base_url=settings.worker_url,
            headers={"Authorization": f"Bearer {settings.worker_token}"},
            timeout=timeout,
        )
        return cls(http, settings.worker_retry_window_s)

    def is_warm(self, window_s: float) -> bool:
        """Whether the worker answered within the last `window_s` seconds (so it's up)."""
        return self.last_answered is not None and self.clock() - self.last_answered < window_s

    async def close(self) -> None:
        await self.http.aclose()

    async def analyze(self, audio: bytes, params: Mapping[str, Any]) -> dict[str, Any]:
        """The worker's result for one recording. Raises AppError."""
        response = await self._post("/v1/analyze", params=dict(params), content=audio)
        if response.status_code == status.HTTP_200_OK:
            result: dict[str, Any] = response.json()
            return result
        if response.status_code in PASS_THROUGH:
            raise _worker_error(response)
        logger.error("worker refused", extra={"status": response.status_code})
        raise unavailable()

    async def warm(self) -> bool:
        """Wake the worker; True once it answers ready."""
        response = await self._post("/v1/warm")
        return response.status_code == status.HTTP_200_OK

    async def _post(self, path: str, **kwargs: Any) -> httpx.Response:
        """POST, retrying while the worker starts, up to the retry window."""
        deadline = self.clock() + self.retry_window_s
        attempt = 0
        while True:
            try:
                response = await self.http.post(path, **kwargs)
                if response.status_code not in RETRY_STATUSES:
                    if response.status_code != status.HTTP_401_UNAUTHORIZED:
                        self.last_answered = self.clock()
                    return response
            except httpx.ReadTimeout as exc:
                raise timed_out() from exc  # it may be running: never send it twice
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
                pass  # it never got the request: safe to send again
            except httpx.TransportError as exc:
                raise unavailable() from exc  # it may have got it: don't send it twice
            wait = BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)]
            if self.clock() + wait > deadline:
                raise unavailable()
            attempt += 1
            await self.sleep(wait)
