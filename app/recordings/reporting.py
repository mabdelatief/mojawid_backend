"""Reporting a kept recording's result as wrong: once per recording, by any tester (closed
testing). The report joins the bad-result reports on the admin page; its audio is the kept
recording, so there's no consent step and no upload. The unique key on report.recording_id is
what makes it "once", even for two testers pressing at the same moment."""

import uuid
from typing import Any

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.client import Client
from app.config import Settings
from app.contracts.recordings import RecordingReportCreate, RecordingReportCreated
from app.db.models.analysis import RUNNING
from app.db.models.recording import Recording
from app.db.models.report import Report
from app.errors import AppError
from app.recordings.service import not_found, shown_report
from app.repositories.recording_repo import RecordingRepo
from app.repositories.report_repo import ReportRepo
from app.services.rate_limit_service import Limit, RateLimitService

DAY = 86400


def already_reported() -> AppError:
    return AppError(
        "recording_already_reported",
        "This recording's result was already reported.",
        status.HTTP_409_CONFLICT,
    )


def _shown(row: Recording) -> dict[str, Any]:
    """What the reporters saw: the result, or the error when the analysis failed."""
    if row.result is not None:
        return row.result
    return {"error": {"code": row.error_code, "message": row.error_message}}


class RecordingReporter:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.recordings = RecordingRepo(session)
        self.reports = ReportRepo(session)

    async def report(
        self, client: Client, recording_id: uuid.UUID, body: RecordingReportCreate
    ) -> RecordingReportCreated:
        found = await self.recordings.get_with_report(recording_id)
        if found is None:
            raise not_found()
        row, existing = found
        if existing is not None:
            raise already_reported()
        if row.status == RUNNING:
            raise AppError("recording_not_analysed", "This recording is still being analysed.", 409)
        await self._count(client)
        report = Report(
            id=uuid.uuid4(), install_hash=client.install_hash, platform=client.platform,
            category=body.category, word=body.word.model_dump() if body.word else None,
            note=body.note, analysis_client_id=row.client_id, result=_shown(row),
            reading=_reading(row), app_version=body.app_version, recording_id=row.id,
            reporter_email=client.tester_email,
        )  # fmt: skip
        self.reports.add(report)
        try:
            await self.session.commit()
        except IntegrityError as exc:  # another tester's report won the race
            await self.session.rollback()
            raise already_reported() from exc
        await self.session.refresh(report)
        return RecordingReportCreated(id=report.id, report=shown_report(report))

    async def _count(self, client: Client) -> None:
        s = self.settings
        await RateLimitService.for_session(self.session).check([
            Limit(f"report:install:{client.install_hash}", s.reports_per_install_day, DAY),
            Limit(f"report:ip:{client.ip_hash}", s.reports_per_ip_day, DAY),
        ])  # fmt: skip


def _reading(row: Recording) -> dict[str, Any]:
    raw = row.request.get("reading")
    return raw if isinstance(raw, dict) else {"raw": raw}
