"""The request id: a contextvar set by a small ASGI middleware, echoed in the response header and
stamped on every log line and error body."""

import re
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
# A caller-supplied id is only reused when it looks like one; anything else is replaced, so a
# header can't inject text into logs.
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def get_request_id() -> str | None:
    """The current request's id, if inside a request."""
    return _request_id.get()


class RequestIdMiddleware:
    """Assign each request an id (reusing a well-formed incoming one) and echo it back."""

    def __init__(self, app: ASGIApp, header_name: str) -> None:
        self.app = app
        self.header = header_name.lower().encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope["headers"]).get(self.header, b"").decode("latin-1")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        token = _request_id.set(request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((self.header, request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            _request_id.reset(token)
