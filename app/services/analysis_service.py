"""Analyses: limits, idempotency and the worker call (docs/contracts/api.md, "Analyses").

A recording is analysed once per (install, client_id); the result is kept a day, so a resend
after a dropped connection gets it back without a second GPU run or a second count against the
limits. Claims are committed before the worker is called, so of two simultaneous sends one runs
and the other gets 409. The recording is passed through from memory and never stored or logged.
"""

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.client import Client
from app.config import Settings
from app.contracts.analysis import AnalysisPending, AnalysisRequest, AnalysisResult
from app.db.models.analysis import DONE, FAILED, Analysis
from app.errors import AppError
from app.repositories.analysis_repo import AnalysisRepo
from app.services.rate_limit_service import Limit, RateLimitService

logger = logging.getLogger("mojawid.analyses")

TRANSIENT = {"analysis_unavailable", "analysis_timeout"}  # the app may simply send it again
HOUR, DAY = 3600, 86400


class Worker(Protocol):
    """What the service needs from the worker (WorkerClient, or a fake in tests)."""

    async def analyze(self, audio: bytes, params: dict[str, Any]) -> dict[str, Any]: ...


def in_progress() -> AppError:
    return AppError(
        "analysis_in_progress",
        "This recording is still being analysed; ask for its result.",
        status.HTTP_409_CONFLICT,
    )


def not_found() -> AppError:
    return AppError(
        "analysis_not_found", "No analysis with this client_id.", status.HTTP_404_NOT_FOUND
    )


def _stored_error(row: Analysis) -> AppError:
    return AppError(
        row.error_code or "analysis_failed",
        row.error_message or "The analysis failed.",
        row.error_status or status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


class AnalysisService:
    def __init__(self, session: AsyncSession, settings: Settings, worker: Worker) -> None:
        self.session = session
        self.settings = settings
        self.worker = worker
        self.repo = AnalysisRepo(session)

    async def analyse(
        self, client: Client, request: AnalysisRequest, audio: bytes
    ) -> AnalysisResult:
        """The result for one recording. Raises AppError."""
        self._check_text(request)
        key = (client.install_hash, request.client_id)
        row = await self._current(*key)
        if row is not None:
            if row.status != "running" or not await self._take_over(*key):
                return self._replay(row)
        else:
            await self._count(client)
            if not await self._claim(*key):
                return self._replay(await self._current(*key))
        return await self._run(key, request, audio)

    async def result(
        self, client: Client, client_id: uuid.UUID
    ) -> AnalysisResult | AnalysisPending:
        """GET: the result, still running, the stored error, or 404."""
        row = await self._current(client.install_hash, client_id)
        if row is None:
            raise not_found()
        if row.status == "running":
            return AnalysisPending()
        return self._replay(row)

    def _check_text(self, request: AnalysisRequest) -> None:
        if request.mode != "manual" or request.aya_start is None:
            return
        count = (request.aya_end or request.aya_start) - request.aya_start + 1
        if count > self.settings.max_ayat_manual:
            raise AppError(
                "too_many_ayat", f"At most {self.settings.max_ayat_manual} ayat per recording."
            )

    async def _current(self, install_hash: str, client_id: uuid.UUID) -> Analysis | None:
        """The row, unless it is past its day (then it is dropped, as the purge would)."""
        row = await self.repo.get(install_hash, client_id)
        ttl = timedelta(hours=self.settings.analysis_result_ttl_hours)
        if row is not None and row.created_at < datetime.now(UTC) - ttl:
            await self.repo.release(install_hash, client_id)
            await self.session.commit()
            return None
        return row

    def _replay(self, row: Analysis | None) -> AnalysisResult:
        if row is None:
            raise in_progress()  # claimed by a simultaneous send, then dropped: rare
        if row.status == DONE and row.result is not None:
            return AnalysisResult.model_validate(row.result)
        if row.status == FAILED:
            raise _stored_error(row)
        raise in_progress()

    async def _take_over(self, install_hash: str, client_id: uuid.UUID) -> bool:
        stale = datetime.now(UTC) - timedelta(seconds=self.settings.analysis_stale_after_s)
        taken = await self.repo.take_over(install_hash, client_id, stale)
        await self.session.commit()
        return taken

    async def _claim(self, install_hash: str, client_id: uuid.UUID) -> bool:
        claimed = await self.repo.claim(install_hash, client_id)
        await self.session.commit()
        return claimed

    async def _count(self, client: Client) -> None:
        """The caller's limits, then the GPU budget for everyone (counted only if those pass)."""
        s = self.settings
        limiter = RateLimitService.for_session(self.session)
        await limiter.check([
            Limit(f"analysis:install:{client.install_hash}", s.analyses_per_install_hour, HOUR),
            Limit(f"analysis:install-day:{client.install_hash}", s.analyses_per_install_day, DAY),
            Limit(f"analysis:ip:{client.ip_hash}", s.analyses_per_ip_hour, HOUR),
        ])  # fmt: skip
        try:
            await limiter.check([Limit("analysis:all", s.analyses_per_day_total, DAY)])
        except AppError as exc:
            raise AppError(
                "analysis_busy",
                "The service has reached today's analyses; try again later.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                headers=exc.headers,
            ) from exc

    async def _run(
        self, key: tuple[str, uuid.UUID], request: AnalysisRequest, audio: bytes
    ) -> AnalysisResult:
        t0 = time.perf_counter()
        try:
            raw = await self.worker.analyze(audio, request.worker_params())
            result = AnalysisResult.model_validate(raw)
        except AppError as exc:
            await self._failed(key, exc)
            _log(request, exc.code, t0)
            raise
        except Exception:
            await self.repo.release(*key)
            await self.session.commit()
            _log(request, "internal_error", t0)
            raise
        await self.repo.finish(*key, result.model_dump(mode="json"))
        await self.session.commit()
        _log(request, "ok", t0)
        return result

    async def _failed(self, key: tuple[str, uuid.UUID], exc: AppError) -> None:
        if exc.code in TRANSIENT:
            await self.repo.release(*key)
        else:
            await self.repo.fail(*key, exc.code, exc.message, exc.status_code)
        await self.session.commit()


def _log(request: AnalysisRequest, outcome: str, t0: float) -> None:
    """One line per analysis: never the recording, the reading settings or the result."""
    ms = round((time.perf_counter() - t0) * 1000)
    logger.info("analysis", extra={"mode": request.mode, "outcome": outcome, "ms": ms})
