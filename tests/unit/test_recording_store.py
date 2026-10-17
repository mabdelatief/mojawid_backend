"""The kept recordings' file store and who-made-it (app/recordings/store.py, app/access)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.access.client import tester_email as login_email
from app.config import Settings
from app.recordings.store import RecordingStore, file_name_for, media_type


def test_saved_exactly_as_sent_under_its_own_name(tmp_path: Path) -> None:
    store = RecordingStore(tmp_path / "recordings")
    rid = uuid.uuid4()
    name = file_name_for(rid, media_type("audio/webm;codecs=opus"))
    store.save(name, b"\x1a\x45\xdf\xa3 webm")
    assert name == f"{rid}.webm"
    assert store.path(name).read_bytes() == b"\x1a\x45\xdf\xa3 webm"
    assert [p.name for p in (tmp_path / "recordings").iterdir()] == [name]  # no partial left
    store.delete(name)
    store.delete(name)  # already gone: fine
    assert not store.path(name).exists()


def test_types_and_names() -> None:
    assert media_type(None) == "application/octet-stream"
    assert media_type(" Audio/MP4 ") == "audio/mp4"
    assert file_name_for(uuid.UUID(int=1), "application/octet-stream").endswith(".bin")


@pytest.mark.parametrize("bad", ["../x.wav", "a/b.wav", ".hidden.partial"])
def test_no_path_from_outside(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError):
        RecordingStore(tmp_path).path(bad)


def test_the_login_email_is_believed_only_from_a_trusted_proxy() -> None:
    s = Settings(trusted_proxy_networks=("172.30.0.10/32",))
    h = {"cf-access-authenticated-user-email": " M.Tester@Example.com "}
    assert login_email(s, "172.30.0.10", h) == "m.tester@example.com"
    assert login_email(s, "192.168.1.50", h) is None  # anyone else could write the header
    assert login_email(s, "172.30.0.10", {}) is None
    assert login_email(s, "172.30.0.10", {"cf-access-authenticated-user-email": "x"}) is None
