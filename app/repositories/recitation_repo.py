"""Reciters and their ayah timings."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.recitation import Recitation, RecitationAyahTiming


class RecitationRepo:
    """Read-only access to the reciter tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def offered(self) -> Sequence[Recitation]:
        """Every reciter the app may offer, by slug."""
        stmt = select(Recitation).where(Recitation.offered.is_(True)).order_by(Recitation.slug)
        return (await self.session.scalars(stmt)).all()

    async def by_slug(self, slug: str) -> Recitation | None:
        """An offered reciter by slug."""
        stmt = select(Recitation).where(Recitation.slug == slug, Recitation.offered.is_(True))
        return await self.session.scalar(stmt)

    async def timings(
        self, recitation_id: int, surah: int, first: int, last: int
    ) -> Sequence[RecitationAyahTiming]:
        """Ayat first..last (inclusive) of a surah, in order."""
        stmt = (
            select(RecitationAyahTiming)
            .where(
                RecitationAyahTiming.recitation_id == recitation_id,
                RecitationAyahTiming.surah == surah,
                RecitationAyahTiming.ayah.between(first, last),
            )
            .order_by(RecitationAyahTiming.ayah)
        )
        return (await self.session.scalars(stmt)).all()
