#!/usr/bin/env python3
"""PreToolUse Edit/Write guard: never edit a migration that already shipped.

The rule (CLAUDE.md "Database & migrations"): a migration file that exists on `origin/main` may
already have run on the production database and will never run there again. Editing it changes
nothing anywhere except fresh databases, which then diverge from production. A schema or data
change needs a NEW migration instead.

  - BLOCK any Edit/Write/MultiEdit whose target is a `migrations/versions/*.py` file that exists
    on `origin/main`.
  - Files not yet on `origin/main` (work in progress) may be edited freely.

Exit 2 = block (stderr becomes the refusal reason).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSIONS_RE = re.compile(r"/migrations/versions/[^/]+\.py$")


def _repo_relative(path_text: str) -> str | None:
    try:
        return str(Path(path_text).resolve().relative_to(REPO_ROOT))
    except (ValueError, OSError):
        return None


def _exists_on_origin_main(rel_path: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"origin/main:{rel_path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0  # malformed input — don't block
    tool = payload.get("tool_name") or payload.get("tool")
    if tool not in {"Edit", "Write", "MultiEdit"}:
        return 0
    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if not file_path or not VERSIONS_RE.search(file_path.replace("\\", "/")):
        return 0
    rel_path = _repo_relative(file_path)
    if rel_path is None or not _exists_on_origin_main(rel_path):
        return 0
    print(
        f"BLOCKED: {rel_path} exists on origin/main — it may already have run on the production "
        "database and will never run there again, so editing it only makes fresh databases "
        "diverge. Write a NEW migration after the current head instead (/new-migration). See "
        'CLAUDE.md "Database & migrations".',
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
