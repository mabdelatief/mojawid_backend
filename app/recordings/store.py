"""The recordings' audio files: the upload exactly as sent, one file per recording, in
`recordings_dir` on this machine (docs/deploy-laptop.md).

A file is written under a temporary name in the same folder and then renamed, so a half-written
file never carries a recording's name. Files are named by the recording's id only; nothing a
client sends becomes part of a path.
"""

import os
import uuid
from pathlib import Path

EXTENSIONS = {
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/webm": "webm",
    "video/webm": "webm",
    "audio/ogg": "ogg",
    "audio/opus": "opus",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/flac": "flac",
}


def media_type(header: str | None) -> str:
    """The content type as stored: the type itself, without parameters (codecs=…)."""
    value = (header or "").split(";")[0].strip().lower()
    return value[:100] or "application/octet-stream"


def file_name_for(recording_id: uuid.UUID, content_type: str) -> str:
    return f"{recording_id}.{EXTENSIONS.get(content_type, 'bin')}"


class RecordingStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, file_name: str, audio: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        final = self.path(file_name)
        partial = final.with_name(f".{file_name}.partial")
        with open(partial, "wb") as f:
            f.write(audio)
            f.flush()
            os.fsync(f.fileno())
        os.replace(partial, final)

    def path(self, file_name: str) -> Path:
        if "/" in file_name or file_name.startswith("."):
            raise ValueError("not a recording file name")
        return self.root / file_name

    def delete(self, file_name: str) -> None:
        self.path(file_name).unlink(missing_ok=True)
