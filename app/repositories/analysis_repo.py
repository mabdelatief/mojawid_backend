"""Analysis rows (idempotency). Each write is one statement, so two requests with the same
client_id can't both claim it. Never commits: the service owns the transaction."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import DONE, FAILED, RUNNING, Analysis


class AnalysisRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _key(install_hash: str, client_id: uuid.UUID) -> Any:
        return (Analysis.install_hash == install_hash) & (Analysis.client_id == client_id)

    async def get(self, install_hash: str, client_id: uuid.UUID) -> Analysis | None:
        stmt = select(Analysis).where(self._key(install_hash, client_id))
        found: Analysis | None = await self.session.scalar(stmt)
        return found

    async def claim(self, install_hash: str, client_id: uuid.UUID) -> bool:
        """Insert a running row; False when one already exists."""
        stmt = (
            insert(Analysis)
            .values(install_hash=install_hash, client_id=client_id, status=RUNNING)
            .on_conflict_do_nothing(index_elements=[Analysis.install_hash, Analysis.client_id])
            .returning(Analysis.client_id)
        )
        return (await self.session.scalar(stmt)) is not None

    async def take_over(
        self, install_hash: str, client_id: uuid.UUID, stale_before: datetime
    ) -> bool:
        """Claim a running row left before `stale_before` (its worker call died); False if it
        isn't there or isn't stale."""
        stmt = (
            update(Analysis)
            .where(self._key(install_hash, client_id))
            .where(Analysis.status == RUNNING, Analysis.updated_at < stale_before)
            .values(updated_at=func.now())
            .returning(Analysis.client_id)
        )
        return (await self.session.scalar(stmt)) is not None

    async def finish(self, install_hash: str, client_id: uuid.UUID, result: dict[str, Any]) -> None:
        stmt = (
            update(Analysis)
            .where(self._key(install_hash, client_id))
            .values(status=DONE, result=result, updated_at=func.now())
        )
        await self.session.execute(stmt)

    async def fail(
        self, install_hash: str, client_id: uuid.UUID, code: str, message: str, status: int
    ) -> None:
        """Keep a final error (the recording's own fault), so a resend gets it again."""
        stmt = (
            update(Analysis)
            .where(self._key(install_hash, client_id))
            .values(
                status=FAILED,
                error_code=code,
                error_message=message,
                error_status=status,
                updated_at=func.now(),
            )
        )
        await self.session.execute(stmt)

    async def release(self, install_hash: str, client_id: uuid.UUID) -> None:
        """Drop a claim after a passing failure, so the app can simply send it again."""
        await self.session.execute(delete(Analysis).where(self._key(install_hash, client_id)))

    async def delete_before(self, cutoff: datetime) -> int:
        """Drop analyses made before `cutoff`; returns how many."""
        stmt = delete(Analysis).where(Analysis.created_at < cutoff).returning(Analysis.client_id)
        return len((await self.session.execute(stmt)).all())
