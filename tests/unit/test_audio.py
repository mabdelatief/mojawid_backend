"""Decoding an upload in memory: the formats phones and browsers send, the errors, and that
nothing is ever written to disk."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest

from app.engine.pipeline.audio import as_saved, decode_audio
from app.engine.pipeline.errors import AudioTooLong, AudioTooShort, AudioUnreadable


def tone(seconds: float, fmt: str, tmp: Path) -> bytes:
    """A 440 Hz tone encoded as `fmt`. MP4/M4A can't be written to a pipe, so it goes through a
    file here (test fixture only), with its index at the end as phones write it."""
    src = ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    if fmt == "m4a":
        out = tmp / "tone.m4a"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", *src, "-c:a", "aac", str(out)], check=True
        )
        return out.read_bytes()
    args = {"mp3": ["-f", "mp3"], "webm": ["-c:a", "libopus", "-f", "webm"], "wav": ["-f", "wav"]}[
        fmt
    ]
    return subprocess.run(
        ["ffmpeg", "-loglevel", "error", *src, *args, "pipe:1"], check=True, capture_output=True
    ).stdout


@pytest.mark.parametrize("fmt", ["m4a", "mp3", "webm", "wav"])
def test_formats_decode_from_memory(fmt: str, tmp_path: Path) -> None:
    data = tone(2.0, fmt, tmp_path)
    if fmt == "m4a":
        assert data.find(b"moov") > len(data) // 2  # the index really is at the end
    wave = decode_audio(data)
    assert wave.dtype == np.float32
    assert abs(wave.size / 16000 - 2.0) < 0.1
    assert 0.05 < float(np.abs(wave).max()) <= 1.0


def test_nothing_is_written_to_tmp(tmp_path: Path) -> None:
    data = tone(2.0, "m4a", tmp_path)
    before = set(os.listdir(tempfile.gettempdir()))
    decode_audio(data)
    assert set(os.listdir(tempfile.gettempdir())) - before == set()


@pytest.mark.parametrize("data", [b"", b"not audio at all" * 100])
def test_unreadable(data: bytes) -> None:
    with pytest.raises(AudioUnreadable):
        decode_audio(data)


def test_too_short_and_too_long(tmp_path: Path) -> None:
    with pytest.raises(AudioTooShort):
        decode_audio(tone(0.1, "mp3", tmp_path))
    with pytest.raises(AudioTooLong):
        decode_audio(tone(61.0, "mp3", tmp_path))


def test_error_messages_never_quote_ffmpeg() -> None:
    with pytest.raises(AudioUnreadable) as err:
        decode_audio(b"\x00\x01garbage")
    assert "ffmpeg" not in err.value.message.lower()
    assert "/dev/fd" not in err.value.message


def test_as_saved_rounds_to_16_bit() -> None:
    wave = np.array([0.0, 0.5, -1.0, 1.0, 0.123456789], dtype=np.float32)
    out = as_saved(wave)
    assert out[2] == -1.0
    assert out[3] == 32767 / 32768
    assert np.allclose(out * 32768, np.round(out * 32768))
