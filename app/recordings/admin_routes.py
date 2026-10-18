"""The admin page's recordings: the newest ones, each playable, and «delete» (the row and the
file), for when a tester asks for theirs to be removed. Behind the admin login, like the reports
(app/reports/admin_auth.py); the admin page is reached on the home Wi-Fi only."""

import uuid
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import SettingsDep
from app.config import Settings
from app.db.models.recording import Recording
from app.db.models.report import Report
from app.recordings.routes import ServiceDep
from app.recordings.service import item_of
from app.reports.admin_auth import check_csrf, csrf_token, require_admin

router = APIRouter(
    prefix="/admin/recordings", include_in_schema=False, dependencies=[Depends(require_admin)]
)
templates = Jinja2Templates(
    directory=[Path(__file__).parent / "templates", Path(__file__).parents[1] / "reports/templates"]
)
PAGE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; media-src 'self'; "
    "form-action 'self'; frame-ancestors 'none'",
}
SHOWN = 200


def row_of(rec: Recording, report: Report | None, settings: Settings) -> dict[str, Any]:
    item = item_of(rec, report)
    t = item.text
    return {
        "item": item,
        "email": rec.tester_email or "—",
        "text": f"{t.sura or '?'}:{t.aya_start or '?'}–{t.aya_end or '?'}",
        "kb": round(rec.size_bytes / 1024),
        "csrf_delete": csrf_token(settings, f"delete-recording:{rec.id}"),
        "report_id": report.id if report is not None else None,
    }


async def _form_token(request: Request) -> str:
    fields = parse_qs((await request.body()).decode("utf-8", "replace"))
    return (fields.get("csrf") or [""])[0]


@router.get("", response_class=HTMLResponse)
async def admin_recordings(
    request: Request, service: ServiceDep, settings: SettingsDep
) -> HTMLResponse:
    rows = [row_of(r, rep, settings) for r, rep in await service.recent(SHOWN)]
    context = {"rows": rows, "shown": SHOWN}
    return templates.TemplateResponse(request, "recordings.html", context, headers=PAGE_HEADERS)


@router.get("/{recording_id}/audio", response_class=FileResponse)
async def admin_recording_audio(recording_id: uuid.UUID, service: ServiceDep) -> FileResponse:
    path, media_type = await service.audio(recording_id)
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.post(
    "/{recording_id}/delete",
    status_code=status.HTTP_303_SEE_OTHER,
    response_class=RedirectResponse,
)
async def admin_delete_recording(
    recording_id: uuid.UUID,
    token: Annotated[str, Depends(_form_token)],
    service: ServiceDep,
    settings: SettingsDep,
) -> RedirectResponse:
    check_csrf(settings, f"delete-recording:{recording_id}", token)
    await service.delete(recording_id)
    return RedirectResponse("/admin/recordings", status.HTTP_303_SEE_OTHER)
