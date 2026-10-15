#!/usr/bin/env python3
"""PreToolUse advisory: warn *before* an edit pushes a file toward the 500-line cap.

The Stop hook (enforce_discipline.py -> discipline_scan.check_file_length) only flags an
oversized file once the edit is done, which turns the module split into an end-of-turn
scramble. This hook projects the file's post-edit line count and, when it nears or passes the
cap, adds a non-blocking note so the split can be planned into the change.

Scope mirrors discipline_scan.check_file_length: .py files under the scanned roots, excluding
Alembic migration versions.

Never blocks. It returns permissionDecision "defer" (not "allow") so the normal permission
system still applies. On any error or non-applicable call it exits 0 silently.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scan_common import FILE_CAP, LENGTH_ROOTS, REPO_ROOT

# Warn early enough that there's runway to plan a split, not at 501.
WARN_AT = FILE_CAP - 50


def _in_scope(path: Path) -> bool:
    p = str(path)
    if not p.endswith(".py") or "/migrations/versions/" in p:
        return False
    return any(path.is_relative_to(REPO_ROOT / root) for root in LENGTH_ROOTS)


def _current_lines(path: Path) -> int:
    try:
        return len(path.read_text().splitlines())
    except (OSError, UnicodeDecodeError):
        return 0


def _projected_lines(tool: str, tool_input: dict, path: Path) -> int | None:
    """Best-effort post-edit line count. None if it can't be estimated."""
    if tool == "Write":
        content = tool_input.get("content")
        return None if content is None else len(content.splitlines())
    if tool == "Edit":
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        return _current_lines(path) + (new.count("\n") - old.count("\n"))
    if tool == "MultiEdit":
        delta = sum(
            e.get("new_string", "").count("\n") - e.get("old_string", "").count("\n")
            for e in tool_input.get("edits") or []
        )
        return _current_lines(path) + delta
    return None


def _advisory(path: Path, projected: int) -> str | None:
    rel = path.relative_to(REPO_ROOT)
    if projected > FILE_CAP:
        return (
            f"⚠ This edit puts {rel} at ~{projected} lines, over the {FILE_CAP}-line cap. The "
            "Stop hook will block until it's split. Plan the split into focused modules as part "
            "of THIS change rather than after."
        )
    if projected >= WARN_AT:
        return (
            f"Heads-up: {rel} would be ~{projected} lines after this edit ({FILE_CAP}-line cap). "
            "If more is coming, decide now where to split it into focused modules — don't append "
            "until it trips the Stop hook."
        )
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    tool = payload.get("tool_name") or payload.get("tool")
    if tool not in {"Edit", "Write", "MultiEdit"}:
        return 0
    tool_input = payload.get("tool_input") or {}
    fp = tool_input.get("file_path")
    if not fp:
        return 0
    path = Path(fp).resolve()
    if not _in_scope(path):
        return 0
    projected = _projected_lines(tool, tool_input, path)
    message = None if projected is None else _advisory(path, projected)
    if message is None:
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "defer",
                    "additionalContext": message,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
