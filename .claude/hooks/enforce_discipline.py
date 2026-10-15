#!/usr/bin/env python3
"""Stop hook: refuse to end the turn while discipline rules are violated.

Wraps .claude/scripts/discipline_scan.py, including mypy --strict on the changed files. On
violations it outputs Claude Code's block JSON; otherwise it exits 0 and lets the turn end.

Diff-aware: only lines added or modified vs HEAD are checked. A scanner or mypy crash never
blocks the turn.
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import discipline_scan


def main() -> int:
    with contextlib.suppress(OSError):
        sys.stdin.read()  # consume the payload so the producer isn't blocked on the pipe
    try:
        violations = discipline_scan.scan(include_mypy=True)
    except Exception as exc:  # a scanner bug must never block the turn
        print(f"discipline scan skipped (scanner error: {exc})", file=sys.stderr)
        return 0
    if not violations:
        return 0
    reason = (
        "Mojawid backend discipline rules violated. Fix these before ending the turn.\n\n"
        f"{discipline_scan.format_report(violations)}\n\n"
        "Each rule is in CLAUDE.md. Fix the underlying code; do not edit the hook or the scanner "
        "to suppress it. If a rule itself seems wrong, discuss it with the user first."
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
