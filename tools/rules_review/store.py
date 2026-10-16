"""The teachers' answers, in SQLite on this laptop (never in the repo): one row per item and
reviewer, plus a log of every change so nothing typed is ever lost to an overwrite."""

from __future__ import annotations

import datetime as dt
import os
import pathlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

DEFAULT_DB = pathlib.Path.home() / ".local" / "share" / "mojawid-review" / "answers.sqlite3"
VERDICTS = ("approve", "correct", "note")

SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
    item_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    verdict TEXT NOT NULL,
    correction TEXT NOT NULL DEFAULT '',
    item_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (item_id, reviewer)
);
CREATE TABLE IF NOT EXISTS answers_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    verdict TEXT,
    correction TEXT,
    item_hash TEXT,
    at TEXT NOT NULL
);
"""


def db_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("MOJAWID_REVIEW_DB", str(DEFAULT_DB)))


@contextmanager
def connect(path: pathlib.Path | None = None) -> Iterator[sqlite3.Connection]:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def all_answers(path: pathlib.Path | None = None) -> list[dict[str, Any]]:
    with connect(path) as conn:
        rows = conn.execute("SELECT * FROM answers ORDER BY item_id, reviewer").fetchall()
    return [dict(r) for r in rows]


def save(item_id: str, reviewer: str, verdict: str, correction: str, item_hash: str,
         path: pathlib.Path | None = None) -> dict[str, Any]:  # fmt: skip
    """Insert or replace one reviewer's answer on one item; logged."""
    if verdict not in VERDICTS:
        raise ValueError(f"unknown verdict {verdict!r}")
    at = _now()
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO answers (item_id, reviewer, verdict, correction, item_hash, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (item_id, reviewer) DO UPDATE SET"
            " verdict = excluded.verdict, correction = excluded.correction,"
            " item_hash = excluded.item_hash, updated_at = excluded.updated_at",
            (item_id, reviewer, verdict, correction, item_hash, at),
        )
        conn.execute(
            "INSERT INTO answers_log (item_id, reviewer, verdict, correction, item_hash, at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (item_id, reviewer, verdict, correction, item_hash, at),
        )
    return {"item_id": item_id, "reviewer": reviewer, "verdict": verdict,
            "correction": correction, "item_hash": item_hash, "updated_at": at}  # fmt: skip


def clear(item_id: str, reviewer: str, path: pathlib.Path | None = None) -> None:
    """Take an answer back (logged with no verdict)."""
    with connect(path) as conn:
        conn.execute("DELETE FROM answers WHERE item_id = ? AND reviewer = ?", (item_id, reviewer))
        conn.execute(
            "INSERT INTO answers_log (item_id, reviewer, at) VALUES (?, ?, ?)",
            (item_id, reviewer, _now()),
        )
