"""Run the purge once, by hand (the API also runs it hourly):

.venv/bin/python -m app.maintenance
"""

import asyncio

from app.config import get_settings
from app.db.session import dispose_engine, get_session_maker
from app.services.maintenance_service import MaintenanceService


async def main() -> None:
    settings = get_settings()
    try:
        async with get_session_maker(settings)() as session:
            purged = await MaintenanceService(session, settings).purge()
        print(
            f"purged {purged.analyses} analyses, {purged.counters} rate-limit counters, "
            f"{purged.reports} reports"
        )
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
