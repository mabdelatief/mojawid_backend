"""Reading an upload as the raw request body, into memory, with a size cap.

Audio is sent as the body itself, never as a form upload: Starlette writes multipart files over
1 MiB to a temporary file on disk, and a recording is never stored (CLAUDE.md).
"""

from fastapi import Request, status

from app.errors import AppError

MAX_UPLOAD_BYTES = 2 * 1024 * 1024


async def read_capped_body(request: Request, limit: int = MAX_UPLOAD_BYTES) -> bytes:
    """The whole body; 413 `audio_too_large` past `limit` (stops reading there)."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise AppError(
            "audio_too_large", "The recording is too large.", status.HTTP_413_CONTENT_TOO_LARGE
        )
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise AppError(
                "audio_too_large", "The recording is too large.", status.HTTP_413_CONTENT_TOO_LARGE
            )
        chunks.append(chunk)
    return b"".join(chunks)
