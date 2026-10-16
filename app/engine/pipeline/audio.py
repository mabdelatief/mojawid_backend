"""The upload → the 16 kHz mono float32 waveform the models expect, without touching disk.

Ported from tajweed_ai `muaalem_lab/audio.py`, which read a saved file. A recording is never
stored (CLAUDE.md), and ffmpeg can't read most M4A/MP4 files from a pipe (the index is often at
the end, so it has to seek). So the upload goes into an in-memory file (Linux memfd: RAM only,
never on disk) that ffmpeg opens as /dev/fd/N and can seek in; the samples come back through a
pipe. ffmpeg's error text is never put in a message (it can quote the input).
"""

import os
import subprocess

import numpy as np

from app.engine.pipeline.errors import AudioTooLong, AudioTooShort, AudioUnreadable
from app.engine.pipeline.pauses import SAMPLE_RATE

MAX_SECONDS = 60.0
MIN_SECONDS = 0.3
FFMPEG_TIMEOUT_S = 30


def _in_memory_file(data: bytes) -> int:
    fd = os.memfd_create("mojawid-audio", os.MFD_CLOEXEC)
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]
    os.lseek(fd, 0, os.SEEK_SET)
    return fd


def _ffmpeg(fd: int, max_seconds: float) -> bytes:
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", f"/dev/fd/{fd}",
        "-t", f"{max_seconds + 0.5:.1f}",
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1",
    ]  # fmt: skip
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=FFMPEG_TIMEOUT_S, check=False, pass_fds=(fd,)
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioUnreadable("Decoding the audio took too long.") from exc
    if proc.returncode != 0:
        raise AudioUnreadable("The file could not be read as audio.")
    return proc.stdout


def decode_audio(data: bytes, max_seconds: float = MAX_SECONDS) -> np.ndarray:
    """The waveform, float32 in [-1, 1]. Raises AudioUnreadable / AudioTooShort / AudioTooLong.
    ffmpeg stops a little past `max_seconds`, so a long upload costs at most that much."""
    if not data:
        raise AudioUnreadable("The upload is empty.")
    fd = _in_memory_file(data)
    try:
        raw = _ffmpeg(fd, max_seconds)
    finally:
        os.close(fd)
    wave = np.frombuffer(raw, dtype=np.float32).copy()
    seconds = wave.size / SAMPLE_RATE
    if wave.size == 0:
        raise AudioUnreadable("The file has no audio in it.")
    if seconds > max_seconds + 0.01:
        raise AudioTooLong(f"The recording is longer than {max_seconds:.0f} seconds.")
    if seconds < MIN_SECONDS:
        raise AudioTooShort("The recording is too short.")
    return wave


def as_saved(wave: np.ndarray) -> np.ndarray:
    """The waveform rounded to 16 bit, as the lab's saved WAV gave it back. The models run on
    this, so results stay the lab's (its goldens were made this way)."""
    pcm = np.clip(np.round(wave * 32768.0), -32768, 32767).astype("<i2")
    out: np.ndarray = pcm.astype(np.float32) / 32768.0
    return out
