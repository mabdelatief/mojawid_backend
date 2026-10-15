#!/usr/bin/env python3
"""PostToolUse formatter for Python edits.

Runs `ruff format` then `ruff check --fix` on the file just touched by Edit/Write/MultiEdit:

  - only .py files inside app/, tests/ or tools/;
  - skip Alembic migration files (they stay as Alembic generated them);
  - skip __pycache__ and .venv.

Uses .venv/bin/ruff if present (the version pinned in pyproject.toml), else system ruff.
Findings ruff can't fix are handed back to Claude as context.

Never blocks. Format failures go to stderr and exit 0 so Claude can continue.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Lines like "path/to/file.py:12:5: PLR0915 Too many statements"
_FINDING_RE = re.compile(r":\d+:\d+:")

REPO_ROOT = Path(__file__).resolve().parents[2]
FORMAT_ROOTS = ("app", "tests", "tools")
VENV_RUFF = REPO_ROOT / ".venv" / "bin" / "ruff"


def _ruff_path() -> str | None:
    if VENV_RUFF.exists():
        return str(VENV_RUFF)
    return shutil.which("ruff")


def _should_format(path: Path) -> bool:
    p = str(path)
    if not path.is_file() or not p.endswith(".py"):
        return False
    if "/__pycache__/" in p or "/.venv/" in p or "/migrations/versions/" in p:
        return False
    return any(path.is_relative_to(REPO_ROOT / root) for root in FORMAT_ROOTS)


def _unfixable_findings(ruff: str, path: Path) -> list[str]:
    """Findings ruff could NOT auto-fix, as concise 'file:line:col: CODE msg' lines."""
    try:
        r = subprocess.run(
            [ruff, "check", "--output-format=concise", str(path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode == 0:
        return []
    return [ln.strip() for ln in r.stdout.splitlines() if _FINDING_RE.search(ln)]


def _emit_context(findings: list[str]) -> None:
    body = "\n".join(f"  {ln}" for ln in findings)
    message = (
        "ruff findings remain after autofix on the file just edited. Fix them now "
        "(the Stop hook gates the per-function caps C901/PLR0911-0915):\n" + body
    )
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": message}}
        )
    )


def _format(ruff: str, path: Path) -> None:
    for cmd in (
        [ruff, "format", "--quiet", str(path)],
        # `--unfixable F401`: never auto-delete unused imports. Deleting them mid-edit breaks the
        # "add the import in one edit, its usage in the next" flow. F401 is still reported via
        # _unfixable_findings, so a stale import is surfaced, not silently removed.
        [ruff, "check", "--fix", "--unfixable", "F401", "--quiet", str(path)],
    ):
        try:
            r = subprocess.run(
                cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=15
            )
            if r.returncode not in (0, 1):  # 1 = lint findings remain, expected
                print(
                    f"format hook: {' '.join(cmd)} exited {r.returncode}\n{r.stderr}",
                    file=sys.stderr,
                )
        except subprocess.TimeoutExpired:
            print(f"format hook: timeout on {path}", file=sys.stderr)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    tool = payload.get("tool_name") or payload.get("tool")
    if tool not in {"Edit", "Write", "MultiEdit"}:
        return 0
    fp = (payload.get("tool_input") or {}).get("file_path")
    if not fp:
        return 0
    path = Path(fp).resolve()
    ruff = _ruff_path()
    if not ruff or not _should_format(path):
        return 0
    _format(ruff, path)
    remaining = _unfixable_findings(ruff, path)
    if remaining:
        _emit_context(remaining)
    return 0


if __name__ == "__main__":
    sys.exit(main())
