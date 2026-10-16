"""The caller's identity for one request.

- `X-Api-Key`: one key per platform, compared in constant time.
- `X-Install-Id`: a random UUID the app creates on first launch. Only its HMAC is kept.
- The client IP: from the proxy's headers when the peer is a trusted proxy, else the socket.
  IPv6 is bucketed by /64, the unit one machine actually gets. Only its HMAC is kept.
"""

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from ipaddress import ip_address, ip_network

from fastapi import status

from app.config import Settings
from app.errors import AppError


@dataclass(frozen=True)
class Client:
    """A verified caller. Hashes are hex HMAC-SHA256 under the identity secret."""

    platform: str
    install_hash: str
    ip_hash: str


def identify(
    settings: Settings,
    api_key: str | None,
    install_id: str | None,
    peer: str | None,
    headers: dict[str, str],
) -> Client:
    """Check the key and the install id, and work out the client IP. Raises AppError."""
    platform = _platform_for(settings, api_key)
    install = _parse_install_id(install_id)
    ip = rate_limit_ip(client_ip(settings, peer, headers))
    return Client(
        platform=platform,
        install_hash=_hmac(settings, f"install:{install}"),
        ip_hash=_hmac(settings, f"ip:{ip}"),
    )


def _platform_for(settings: Settings, api_key: str | None) -> str:
    given = (api_key or "").encode()
    found = None
    for platform, key in settings.api_keys.items():
        # Compare against every key so the time taken doesn't reveal which one nearly matched.
        if hmac.compare_digest(given, key.encode()):
            found = platform
    if found is None:
        raise AppError(
            "invalid_api_key", "Missing or invalid API key.", status.HTTP_401_UNAUTHORIZED
        )
    return found


def _parse_install_id(install_id: str | None) -> uuid.UUID:
    if not install_id:
        raise AppError("missing_install_id", "X-Install-Id is required.")
    try:
        return uuid.UUID(install_id)
    except ValueError as exc:
        raise AppError("invalid_install_id", "X-Install-Id must be a UUID.") from exc


def _hmac(settings: Settings, value: str) -> str:
    return hmac.new(settings.identity_secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def _trusted(settings: Settings, peer: str | None) -> bool:
    try:
        addr = ip_address(peer or "")
    except ValueError:
        return False
    return any(addr in ip_network(net) for net in settings.trusted_proxy_networks)


def client_ip(settings: Settings, peer: str | None, headers: dict[str, str]) -> str:
    """The real client IP. Forwarding headers are the client's to write, so they're believed
    only when the connection came from a trusted proxy."""
    if _trusted(settings, peer):
        forwarded = headers.get("cf-connecting-ip") or headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return peer or "-"


def rate_limit_ip(raw: str) -> str:
    """The IP as a rate-limit unit: IPv6 collapsed to its /64."""
    try:
        addr = ip_address(raw)
    except ValueError:
        return raw
    if addr.version == 6:
        return str(ip_network(f"{addr}/64", strict=False).network_address)
    return str(addr)
