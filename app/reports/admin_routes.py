"""The admin page: the reports, one report with its recording, and «reviewed» (which deletes the
recording at once) or «delete». Server-rendered, behind HTTP Basic (admin_auth.py)."""

import uuid
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import SettingsDep
from app.db.models.report import Report
from app.reports.admin_auth import check_csrf, csrf_token, require_admin
from app.reports.routes import ServiceDep

router = APIRouter(prefix="/admin", include_in_schema=False, dependencies=[Depends(require_admin)])
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

PAGE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; "
    "media-src https://*.linodeobjects.com; form-action 'self'; frame-ancestors 'none'",
}
CATEGORY = {
    "false_mistake": "Marked a mistake I didn't make",
    "missed_mistake": "Missed a mistake I made",
    "wrong_ayat": "Recognised other ayat",
    "other": "Something else",
}


def counted_mistakes(result: dict[str, Any]) -> list[dict[str, Any]]:
    report = result.get("report") or {}
    return [e for e in report.get("errors") or [] if isinstance(e, dict) and e.get("counted")]


def summary_of(report: Report) -> dict[str, Any]:
    text = report.result.get("text") or {}
    word = report.word or {}
    return {
        "report": report,
        "category": CATEGORY.get(report.category or "", "—"),
        "text": f"{text.get('sura', '?')}:{text.get('aya_start', '?')}–{text.get('aya_end', '?')}",
        "word": f"{word['sura']}:{word['aya']} word {word['word']}" if word else "—",
        "summary": report.result.get("summary") or {},
    }


async def _form_token(request: Request) -> str:
    """The csrf field of a small urlencoded form."""
    fields = parse_qs((await request.body()).decode("utf-8", "replace"))
    return (fields.get("csrf") or [""])[0]


@router.get("", response_class=HTMLResponse)
async def admin_reports(request: Request, service: ServiceDep) -> HTMLResponse:
    rows = [summary_of(r) for r in await service.newest()]
    return templates.TemplateResponse(request, "list.html", {"rows": rows}, headers=PAGE_HEADERS)


@router.get("/reports/{report_id}", response_class=HTMLResponse)
async def admin_report(
    report_id: uuid.UUID, request: Request, service: ServiceDep, settings: SettingsDep
) -> HTMLResponse:
    report = await service.get(report_id)
    context = {
        **summary_of(report),
        "audio_url": await service.audio_url(report),
        "mistakes": counted_mistakes(report.result),
        "reading": sorted(report.reading.items()),
        "csrf_reviewed": csrf_token(settings, f"reviewed:{report_id}"),
        "csrf_delete": csrf_token(settings, f"delete:{report_id}"),
    }
    return templates.TemplateResponse(request, "report.html", context, headers=PAGE_HEADERS)


@router.post(
    "/reports/{report_id}/reviewed",
    status_code=status.HTTP_303_SEE_OTHER,
    response_class=RedirectResponse,
)
async def admin_mark_reviewed(
    report_id: uuid.UUID,
    token: Annotated[str, Depends(_form_token)],
    service: ServiceDep,
    settings: SettingsDep,
) -> RedirectResponse:
    """Reviewed: the recording is deleted now."""
    check_csrf(settings, f"reviewed:{report_id}", token)
    await service.mark_reviewed(report_id)
    return RedirectResponse(f"/admin/reports/{report_id}", status.HTTP_303_SEE_OTHER)


@router.post(
    "/reports/{report_id}/delete",
    status_code=status.HTTP_303_SEE_OTHER,
    response_class=RedirectResponse,
)
async def admin_delete_report(
    report_id: uuid.UUID,
    token: Annotated[str, Depends(_form_token)],
    service: ServiceDep,
    settings: SettingsDep,
) -> RedirectResponse:
    check_csrf(settings, f"delete:{report_id}", token)
    await service.delete(report_id)
    return RedirectResponse("/admin", status.HTTP_303_SEE_OTHER)
