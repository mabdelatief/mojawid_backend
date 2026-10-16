"""The admin page's login and CSRF tokens, and the report helpers that need no database."""

from __future__ import annotations

import pytest
from argon2 import PasswordHasher

from app.config import Settings
from app.errors import AppError
from app.reports.admin_auth import check_csrf, csrf_token, password_ok
from app.reports.admin_routes import counted_mistakes
from app.reports.service import content_type_of

HASH = PasswordHasher().hash("a long enough password")


def test_password_check() -> None:
    s = Settings(admin_user="admin", admin_password_hash=HASH)
    assert password_ok(s, "admin", "a long enough password")
    assert not password_ok(s, "admin", "wrong")
    assert not password_ok(s, "root", "a long enough password")
    assert not password_ok(Settings(admin_password_hash="not-a-hash"), "admin", "x")


def test_csrf_tokens_are_per_action() -> None:
    s = Settings()
    check_csrf(s, "reviewed:1", csrf_token(s, "reviewed:1"))
    with pytest.raises(AppError) as err:
        check_csrf(s, "delete:1", csrf_token(s, "reviewed:1"))
    assert (err.value.code, err.value.status_code) == ("csrf_failed", 403)
    other = Settings(identity_secret="another-secret")
    with pytest.raises(AppError):
        check_csrf(other, "reviewed:1", csrf_token(s, "reviewed:1"))


@pytest.mark.parametrize(
    ("header", "kind"),
    [
        ("audio/mp4", "audio/mp4"),
        ("audio/webm; codecs=opus", "audio/webm"),
        ("text/html", "application/octet-stream"),
        (None, "application/octet-stream"),
    ],
)
def test_content_type_of(header: str | None, kind: str) -> None:
    assert content_type_of(header) == kind


def test_counted_mistakes() -> None:
    result = {"report": {"errors": [{"counted": True, "key": "a"}, {"counted": False}, "junk"]}}
    assert counted_mistakes(result) == [{"counted": True, "key": "a"}]
    assert counted_mistakes({}) == []
