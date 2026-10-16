"""The admin page's login: HTTP Basic against an argon2 hash, and a CSRF token on its forms
(a browser sends Basic credentials with cross-site requests too). No hash set: the page doesn't
exist."""

import hashlib
import hmac
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.api.deps import SettingsDep
from app.config import Settings
from app.errors import AppError

_basic = HTTPBasic(auto_error=False)
_hasher = PasswordHasher()


def login_required() -> AppError:
    return AppError(
        "admin_login_required",
        "Log in to the admin page.",
        status.HTTP_401_UNAUTHORIZED,
        headers={"WWW-Authenticate": 'Basic realm="Mojawid admin", charset="UTF-8"'},
    )


def password_ok(settings: Settings, user: str, password: str) -> bool:
    user_ok = hmac.compare_digest(user.encode(), settings.admin_user.encode())
    try:
        matched: bool = _hasher.verify(settings.admin_password_hash, password)
    except (VerificationError, InvalidHashError):
        matched = False
    return user_ok and matched


async def require_admin(
    settings: SettingsDep,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic)],
) -> None:
    if not settings.admin_password_hash:
        raise AppError("not_found", "Not found.", status.HTTP_404_NOT_FOUND)
    if credentials is None or not password_ok(settings, credentials.username, credentials.password):
        raise login_required()


def csrf_token(settings: Settings, action: str) -> str:
    """The token a form for `action` carries (tied to the identity secret)."""
    key = settings.identity_secret.encode()
    return hmac.new(key, f"admin-csrf:{action}".encode(), hashlib.sha256).hexdigest()


def check_csrf(settings: Settings, action: str, token: str) -> None:
    if not hmac.compare_digest(token.encode(), csrf_token(settings, action).encode()):
        raise AppError(
            "csrf_failed", "The form has expired; reload the page.", status.HTTP_403_FORBIDDEN
        )
