"""The review page, at https://tajweed.codavvy.com/mojawid/ through the lab's Cloudflare tunnel
(docs/rules-review/README.md). Cloudflare Access logs the teacher in and passes her email in
`cf-access-authenticated-user-email`; the service listens on 127.0.0.1 only, so nothing else can
reach it or set that header. The engine is not imported: the content is the generated JSON.

    .venv/bin/uvicorn tools.rules_review.server:app --host 127.0.0.1 --port 8300
"""

from __future__ import annotations

import json
import os
import pathlib
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tools.rules_review import store

HERE = pathlib.Path(__file__).resolve().parent
CONTENT = HERE.parents[1] / "docs" / "rules-review" / "content.json"
NAMES = store.DEFAULT_DB.parent / "names.json"  # optional {email: display name}
PREFIX = "/mojawid"
EMAIL_HEADER = "cf-access-authenticated-user-email"
DEV_EMAIL = "MOJAWID_REVIEW_DEV_EMAIL"  # local testing only: an email to use without Cloudflare


class Answer(BaseModel):
    verdict: Literal["approve", "correct", "note"]
    correction: str = Field(default="", max_length=4000)
    hash: str = Field(max_length=64)


class Me(BaseModel):
    email: str
    name: str


_content_cache: dict[str, Any] = {}


def content() -> dict[str, Any]:
    """The generated content, re-read when the file changes."""
    mtime = CONTENT.stat().st_mtime
    if _content_cache.get("mtime") != mtime:
        data = json.loads(CONTENT.read_text())
        ids = {it["id"]: it["hash"] for sec in data["sections"] for it in sec["items"]}
        _content_cache.update(mtime=mtime, data=data, ids=ids)
    return _content_cache


def names() -> dict[str, str]:
    try:
        loaded: dict[str, str] = json.loads(NAMES.read_text())
        return loaded
    except (OSError, ValueError):
        return {}


def display_name(email: str) -> str:
    return names().get(email, email.split("@")[0])


def reviewer(
    email: Annotated[str | None, Header(alias=EMAIL_HEADER)] = None,
) -> str:
    """The logged-in teacher's email; 401 without one."""
    email = (email or os.environ.get(DEV_EMAIL, "")).strip().lower()
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not logged in")
    return email


Reviewer = Annotated[str, Depends(reviewer)]


router = APIRouter(prefix=PREFIX)


@router.get("", include_in_schema=False)
async def bare() -> RedirectResponse:
    return RedirectResponse(f"{PREFIX}/", status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/", include_in_schema=False)
async def page(_: Reviewer) -> FileResponse:
    return FileResponse(HERE / "static" / "index.html")


@router.get("/api/me")
async def me(email: Reviewer) -> Me:
    return Me(email=email, name=display_name(email))


@router.get("/api/content")
async def get_content(_: Reviewer) -> dict[str, Any]:
    data: dict[str, Any] = content()["data"]
    return data


@router.get("/api/answers")
def get_answers(_: Reviewer) -> list[dict[str, Any]]:
    rows = store.all_answers()
    for r in rows:
        r["name"] = display_name(r["reviewer"])
    return rows


@router.put("/api/answers/{item_id}", status_code=status.HTTP_200_OK)
def put_answer(item_id: str, answer: Answer, email: Reviewer) -> dict[str, Any]:
    if item_id not in content()["ids"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such item")
    row = store.save(item_id, email, answer.verdict, answer.correction.strip(), answer.hash)
    row["name"] = display_name(email)
    return row


@router.delete("/api/answers/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_answer(item_id: str, email: Reviewer) -> Response:
    store.clear(item_id, email)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def no_stale_copies(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Every answer revalidated, so an update to the page shows at once (as the lab does)."""
    response = await call_next(request)
    response.headers.setdefault("Cache-Control", "no-cache")
    return response


def create_app() -> FastAPI:
    app = FastAPI(title="Mojawid rules review", docs_url=None, redoc_url=None, openapi_url=None)
    app.middleware("http")(no_stale_copies)
    app.include_router(router)
    app.mount(f"{PREFIX}/static", StaticFiles(directory=HERE / "static"), name="static")
    return app


app = create_app()
