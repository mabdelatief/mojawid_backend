"""Bad-result reports: the one place a user's recording is stored, and only with consent.

The report (what was shown, the reading settings, the user's note) comes first; its audio follows
within `report_upload_window_s`, straight from memory into the private bucket. Marking a report
reviewed deletes the audio at once; the row goes `report_keep_after_review_days` later.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.client import Client
from app.adapters.object_store import ObjectStore
from app.config import Settings
from app.contracts.reports import ReportCreate, ReportCreated
from app.db.models.report import Report
from app.errors import AppError
from app.repositories.report_repo import ReportRepo
from app.services.rate_limit_service import Limit, RateLimitService

DAY = 86400
SIGNED_URL_SECONDS = 300


def not_found() -> AppError:
    return AppError("report_not_found", "No such report.", status.HTTP_404_NOT_FOUND)


def unavailable() -> AppError:
    return AppError(
        "reports_unavailable",
        "Reports can't be received right now.",
        status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def audio_key(report_id: uuid.UUID) -> str:
    return f"reports/{report_id}"


def content_type_of(header: str | None) -> str:
    """The upload's audio type, as the app declared it (anything else is kept as bytes)."""
    value = (header or "").split(";")[0].strip().lower()
    return value if value.startswith("audio/") else "application/octet-stream"


class ReportService:
    def __init__(
        self, session: AsyncSession, settings: Settings, store: ObjectStore | None
    ) -> None:
        self.session = session
        self.settings = settings
        self.store = store
        self.repo = ReportRepo(session)

    def _store(self) -> ObjectStore:
        if self.store is None:
            raise unavailable()
        return self.store

    async def create(self, client: Client, body: ReportCreate) -> ReportCreated:
        if body.consent is not True:
            raise AppError("consent_required", "A report needs the user's consent.")
        self._store()
        s = self.settings
        await RateLimitService.for_session(self.session).check([
            Limit(f"report:install:{client.install_hash}", s.reports_per_install_day, DAY),
            Limit(f"report:ip:{client.ip_hash}", s.reports_per_ip_day, DAY),
        ])  # fmt: skip
        report = Report(
            id=uuid.uuid4(), install_hash=client.install_hash, platform=client.platform,
            category=body.category, word=body.word.model_dump() if body.word else None,
            note=body.note, analysis_client_id=body.analysis_client_id, result=body.result,
            reading=body.reading, app_version=body.app_version,
        )  # fmt: skip
        self.repo.add(report)
        await self.session.commit()
        until = report.created_at + timedelta(seconds=s.report_upload_window_s)
        return ReportCreated(id=report.id, upload_audio_until=until)

    async def upload_audio(
        self, client: Client, report_id: uuid.UUID, audio: bytes, content_type: str | None
    ) -> None:
        """The report's recording: once, from the install that made it, within the window."""
        store = self._store()
        report = await self.repo.get(report_id)
        if report is None or report.install_hash != client.install_hash:
            raise not_found()
        if report.audio_uploaded_at is not None:
            raise AppError("report_audio_exists", "This report already has its recording.", 409)
        window = timedelta(seconds=self.settings.report_upload_window_s)
        if datetime.now(UTC) > report.created_at + window:
            raise AppError("report_upload_expired", "Too late to add the recording.", 410)
        if not audio:
            raise AppError("audio_missing", "The recording is empty.")
        kind = content_type_of(content_type)
        await store.put(audio_key(report_id), audio, kind)
        try:
            await self.repo.set_audio(report_id, audio_key(report_id), kind, len(audio))
            await self.session.commit()
        except Exception:
            await store.delete(audio_key(report_id))
            raise

    # --- the admin page ---------------------------------------------------------------------

    async def newest(self, limit: int = 200) -> Sequence[Report]:
        return await self.repo.newest(limit)

    async def get(self, report_id: uuid.UUID) -> Report:
        report = await self.repo.get(report_id)
        if report is None:
            raise not_found()
        return report

    async def audio_url(self, report: Report) -> str | None:
        if report.audio_key is None or self.store is None:
            return None
        return await self.store.signed_url(report.audio_key, SIGNED_URL_SECONDS)

    async def mark_reviewed(self, report_id: uuid.UUID) -> None:
        """Reviewed: the recording is deleted now; the rest goes after the keep period."""
        report = await self.get(report_id)
        if report.audio_key is not None:
            await self._store().delete(report.audio_key)
        await self.repo.mark_reviewed(report_id)
        await self.session.commit()

    async def delete(self, report_id: uuid.UUID) -> None:
        report = await self.get(report_id)
        if report.audio_key is not None:
            await self._store().delete(report.audio_key)
        await self.repo.delete(report_id)
        await self.session.commit()

    async def purge(self, now: datetime) -> int:
        """Reports whose recording never came, and reports reviewed over the keep period ago.
        The caller commits."""
        s = self.settings
        return await self.repo.delete_stale(
            no_audio_before=now - timedelta(seconds=s.report_upload_window_s),
            reviewed_before=now - timedelta(days=s.report_keep_after_review_days),
        )
