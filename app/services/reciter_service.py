"""The reciters the app offers and their word timings, from our own Postgres. Audio URLs point
at our own bucket; nothing third-party is involved at runtime."""

from fastapi import status
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.contracts.reciters import AyahTiming, Reciter, ReciterList, ReciterTimings, Style
from app.db.models.recitation import Recitation
from app.errors import AppError
from app.repositories.recitation_repo import RecitationRepo

_STYLE: TypeAdapter[Style] = TypeAdapter(Style)


class ReciterService:
    """Reciter list and timings."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.repo = RecitationRepo(session)
        self.settings = settings

    def _template(self, rec: Recitation) -> str:
        return self.settings.audio_base_url + rec.bucket_prefix + rec.file_pattern

    async def list_offered(self) -> ReciterList:
        """Every offered reciter, plus the default one."""
        recs = await self.repo.offered()
        reciters = [
            Reciter(
                slug=r.slug,
                name_ar=r.name_ar,
                name_en=r.name_en,
                style=_STYLE.validate_python(r.style),
                audio_url_template=self._template(r),
            )
            for r in recs
        ]
        return ReciterList(default=self.settings.default_reciter, reciters=reciters)

    async def timings(self, slug: str, surah: int, first: int, last: int) -> ReciterTimings:
        """Timings for ayat first..last of a surah. Errors: not_found, invalid_text_selection."""
        self._check_range(surah, first, last)
        rec = await self.repo.by_slug(slug)
        if rec is None:
            raise AppError("not_found", "No such reciter.", status.HTTP_404_NOT_FOUND)
        rows = await self.repo.timings(rec.id, surah, first, last)
        if len(rows) != last - first + 1:
            raise AppError("invalid_text_selection", "Those ayat aren't in this surah.")
        template = self._template(rec)
        ayat = [
            AyahTiming(
                surah=row.surah,
                ayah=row.ayah,
                audio_url=template.format(surah=row.surah, ayah=row.ayah),
                segments=[(s[0], s[1], s[2], s[3]) for s in row.segments],
            )
            for row in rows
        ]
        return ReciterTimings(reciter=rec.slug, ayat=ayat)

    def _check_range(self, surah: int, first: int, last: int) -> None:
        if not 1 <= surah <= 114 or first < 1 or last < first:
            raise AppError("invalid_text_selection", "Invalid surah or ayah range.")
        if last - first + 1 > self.settings.max_timing_ayat:
            raise AppError(
                "too_many_ayat", f"At most {self.settings.max_timing_ayat} ayat per request."
            )
