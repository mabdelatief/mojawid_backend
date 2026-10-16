"""Caller identity (app key, install id, client IP) and the rate-limit logic, without a DB."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.access.client import client_ip, identify, rate_limit_ip
from app.config import Settings
from app.errors import AppError
from app.services.rate_limit_service import Limit, RateLimitService, window_start

SETTINGS = Settings(api_keys={"android": "key-a", "ios": "key-i"}, identity_secret="s")
INSTALL = "0b8a3f2e-2c1d-4e5f-9a7b-1c2d3e4f5a6b"


def _identify(key: str | None, install: str | None, peer: str = "203.0.113.9") -> object:
    return identify(SETTINGS, key, install, peer, {})


def test_valid_key_and_install_id() -> None:
    client = identify(SETTINGS, "key-i", INSTALL, "203.0.113.9", {})
    assert client.platform == "ios"
    assert INSTALL not in client.install_hash  # only the HMAC is kept
    assert len(client.install_hash) == 64


@pytest.mark.parametrize(
    ("key", "install", "code"),
    [
        (None, INSTALL, "invalid_api_key"),
        ("wrong", INSTALL, "invalid_api_key"),
        ("key-a", None, "missing_install_id"),
        ("key-a", "not-a-uuid", "invalid_install_id"),
    ],
)
def test_rejected_callers(key: str | None, install: str | None, code: str) -> None:
    with pytest.raises(AppError) as err:
        _identify(key, install)
    assert err.value.code == code
    assert err.value.status_code == (401 if code == "invalid_api_key" else 400)


def test_same_install_same_hash_across_requests() -> None:
    a = identify(SETTINGS, "key-a", INSTALL, "203.0.113.9", {})
    b = identify(SETTINGS, "key-a", INSTALL.upper(), "198.51.100.1", {})
    assert a.install_hash == b.install_hash
    assert a.ip_hash != b.ip_hash


def test_forwarding_headers_only_from_trusted_proxy() -> None:
    headers = {"cf-connecting-ip": "198.51.100.7", "x-forwarded-for": "192.0.2.1, 10.0.0.2"}
    assert client_ip(SETTINGS, "127.0.0.1", headers) == "198.51.100.7"
    assert (
        client_ip(SETTINGS, "127.0.0.1", {"x-forwarded-for": "192.0.2.1, 10.0.0.2"}) == "192.0.2.1"
    )
    assert client_ip(SETTINGS, "203.0.113.9", headers) == "203.0.113.9"  # untrusted peer


def test_ipv6_is_bucketed_by_64() -> None:
    assert rate_limit_ip("2001:db8:1:2:aaaa::1") == rate_limit_ip("2001:db8:1:2:bbbb::9")
    assert rate_limit_ip("203.0.113.9") == "203.0.113.9"


def test_production_refuses_dev_secrets() -> None:
    with pytest.raises(ValueError, match="API_KEYS"):
        Settings(environment="production")
    with pytest.raises(ValueError, match="IDENTITY_SECRET"):
        Settings(environment="production", api_keys={"android": "real"})


class FakeCounter:
    """In-memory counters."""

    def __init__(self) -> None:
        self.counts: dict[tuple[str, datetime], int] = {}

    async def increment(self, key: str, window_start: datetime) -> int:
        self.counts[(key, window_start)] = self.counts.get((key, window_start), 0) + 1
        return self.counts[(key, window_start)]


class FakeSession:
    """Records commits."""

    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def test_windows_are_aligned() -> None:
    now = datetime(2026, 10, 16, 13, 47, 12, tzinfo=UTC)
    assert window_start(now, 3600) == datetime(2026, 10, 16, 13, 0, tzinfo=UTC)
    assert window_start(now, 86400) == datetime(2026, 10, 16, tzinfo=UTC)


async def test_limit_allows_then_refuses_with_retry_after() -> None:
    session = FakeSession()
    service = RateLimitService(session, FakeCounter())
    limits = [Limit("install:x", max_requests=2, window_seconds=3600)]
    now = datetime(2026, 10, 16, 13, 59, 30, tzinfo=UTC)
    await service.check(limits, now)
    await service.check(limits, now)
    with pytest.raises(AppError) as err:
        await service.check(limits, now)
    assert err.value.code == "rate_limited"
    assert err.value.status_code == 429
    assert err.value.headers == {"Retry-After": "31"}
    assert session.commits == 3  # a refused request still counts
