"""The migrations build exactly the schema the models describe, and undo cleanly."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Recitation, RecitationAyahTiming
from tests.db.conftest import alembic_config


def test_single_head(migrated_database: str) -> None:
    assert len(ScriptDirectory.from_config(alembic_config()).get_heads()) == 1


def test_models_match_migrations(migrated_database: str) -> None:
    command.check(alembic_config())  # raises if autogenerate would emit anything


def test_downgrade_and_upgrade_again(migrated_database: str) -> None:
    command.downgrade(alembic_config(), "base")
    command.upgrade(alembic_config(), "head")


async def test_timing_rows_round_trip(session: AsyncSession) -> None:
    rec = Recitation(
        slug="test-reciter",
        name_ar="قارئ",
        name_en="Reciter",
        style="murattal",
        bucket_prefix="Test/",
        file_pattern="{surah:03d}{ayah:03d}.mp3",
        timing_source="test",
    )
    session.add(rec)
    await session.flush()
    session.add(
        RecitationAyahTiming(recitation_id=rec.id, surah=1, ayah=1, segments=[[0, 0, 60, 610]])
    )
    await session.flush()
    stored = await session.scalar(
        text("SELECT segments FROM recitation_ayah_timing WHERE recitation_id = :id"),
        {"id": rec.id},
    )
    assert stored == [[0, 0, 60, 610]]
    assert rec.offered is True


async def test_style_is_constrained(session: AsyncSession) -> None:
    session.add(
        Recitation(
            slug="bad-style",
            name_ar="x",
            name_en="x",
            style="hadr",
            bucket_prefix="x/",
            file_pattern="x",
            timing_source="x",
        )
    )
    # A savepoint, so the expected failure doesn't break the test's outer transaction.
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.flush()
