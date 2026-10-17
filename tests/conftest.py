"""Shared by every test folder: kept recordings go to a throwaway folder, never the real one.

Set before collection, because importing app.main builds the app with the cached settings.
"""

import os
import shutil
import tempfile

import pytest

_RECORDINGS = tempfile.mkdtemp(prefix="mojawid-test-recordings-")


def pytest_configure(config: pytest.Config) -> None:
    os.environ["MOJAWID_RECORDINGS_DIR"] = _RECORDINGS


def pytest_unconfigure(config: pytest.Config) -> None:
    shutil.rmtree(_RECORDINGS, ignore_errors=True)
