#!/usr/bin/env python3
"""SessionStart hook — print a compact context block at session start.

Output goes to stdout and is surfaced to the model as additional context. Keep it short:
pointers and state only, never full doc content.

Always exits 0 — never blocks session start.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str], timeout: int = 5) -> str:
    try:
        return subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=timeout
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _dirty_summary() -> tuple[int, int]:
    """(changed, untracked) across the whole repo."""
    changed = untracked = 0
    for line in _run(["git", "status", "--porcelain"]).splitlines():
        if line.startswith("??"):
            untracked += 1
        elif line.strip():
            changed += 1
    return changed, untracked


def _discipline_baseline() -> str:
    try:
        sys.path.insert(0, str(REPO_ROOT / ".claude" / "scripts"))
        import discipline_scan

        v = discipline_scan.scan()
    except Exception as e:  # a scanner bug must never block session start
        return f"discipline scan failed: {e}"
    if not v:
        return "clean (no diff against HEAD violates discipline)"
    counts = ", ".join(f"{k}={len(items)}" for k, items in sorted(v.items()))
    return f"violations in working tree: {counts} — run `/post-pass` for details"


def main() -> int:
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]) or "(detached)"
    commits = _run(["git", "log", "-3", "--pretty=format:%h %s"]).splitlines()
    changed, untracked = _dirty_summary()

    lines = ["# Mojawid backend — session context", "", f"**Branch:** `{branch}`"]
    if changed or untracked:
        lines.append(f"**Working tree:** {changed} modified, {untracked} untracked")
    else:
        lines.append("**Working tree:** clean")
    lines.append(f"**Discipline:** {_discipline_baseline()}")
    lines.append("")
    if commits:
        lines.append("**Recent commits:**")
        lines.extend(f"  - {c}" for c in commits)
        lines.append("")
    lines += [
        "**Read before working on mojawid_backend:**",
        "  - `CLAUDE.md` (hard rules, auto-loaded)",
        "  - `docs/architecture.md` (the agreed architecture and build phases, with status)",
        "  - `docs/dev.md` (docker compose + uv, tests, migrations)",
        "  - `docs/model-and-analysis.md` (the model, the pipeline, what the backend provides)",
        "  - `docs/recitations.md` (reciters, audio bucket, word timings)",
        "  - `../mojawid_flutter/docs/product.md` (the product and its decisions)",
        "",
        "Enforcement layer is in `.claude/`: PreToolUse blockers, PostToolUse formatter,",
        "Stop discipline scan + mypy. `/post-pass` for an on-demand review.",
    ]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
