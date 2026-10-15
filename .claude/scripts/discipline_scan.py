#!/usr/bin/env python3
"""Mojawid backend discipline scanner.

Diff-aware checks against working-tree changes vs HEAD. Used by:
  - .claude/hooks/enforce_discipline.py  (Stop hook, blocks turn end; runs mypy too)
  - .claude/hooks/session_start.py       (one-line status)
  - .claude/skills/post-pass/SKILL.md     (on-demand report)

Each rule maps to a rule in CLAUDE.md. Only lines added or modified vs HEAD are checked, so
existing code is left alone until it's touched. The rules live in rules_code.py (Python /
FastAPI / SQLAlchemy), rules_repo.py (caps, tests, migrations, pyproject) and rules_mojawid.py
(never store a recording, nothing third-party at runtime, pinned models).

    python3 .claude/scripts/discipline_scan.py [--mypy]
"""

from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rules_code
import rules_mojawid
import rules_repo
from scan_common import APP, REPO_ROOT, TESTS, added_lines, changed_files, tool_path, under

_HEADERS = {
    "suppressions": "No new `# noqa` / `# type: ignore` — fix the code or the type",
    "lazy_raise": 'Every relationship() declares lazy="raise"',
    "repo_commit": "Repositories never commit — services own the transaction",
    "httpexception": "Errors go through AppError, never HTTPException",
    "route_handlers": "Routes: async def, status_code= on mutations, response_model= on data",
    "include_router": "Routers are mounted only in app/api/router.py",
    "separate_metadata": "One Base.metadata (app/db/base.py)",
    "legacy_patterns": "No Pydantic v1 / SQLAlchemy 1.x / Optional[...] patterns",
    "no_stored_audio": "Never store a recording (CLAUDE.md)",
    "no_third_party": "Nothing third-party at runtime; HTTP clients only in app/adapters/",
    "pinned_models": "Models stay pinned (app/model_pins.py)",
    "file_length": "File too long — split into focused modules",
    "function_length": "Function too long — extract collaborators",
    "function_caps": "Per-function caps exceeded — extract collaborators, never # noqa",
    "test_layout": "Tests live under tests/unit, tests/db or tests/integration",
    "tests_for_routes": "A new or changed route ships with a test",
    "alembic_single_head": "One Alembic head — add a merge revision",
    "pyproject": "pyproject.toml: no new per-file-ignores; patched quran-transcript only",
    "mypy": "mypy --strict on the changed files",
}


def _rel(path: Path | None) -> str:
    return str(path.relative_to(REPO_ROOT)) if path else ""


def run_mypy(changed: list[Path]) -> list[str]:
    """mypy --strict (config in pyproject) on changed files under app/ and tests/.

    Returns findings; a crash or a missing mypy returns [] so a tool failure never blocks."""
    mypy = tool_path("mypy")
    targets = [str(f) for f in changed if under(f, APP) or under(f, TESTS)]
    if mypy is None or not targets:
        return []
    try:
        r = subprocess.run(
            [mypy, "--no-error-summary", "--hide-error-context", *targets],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode not in (0, 1):  # 2 = mypy itself failed (config, crash)
        print(f"mypy skipped (exit {r.returncode}): {r.stderr.strip()[:300]}", file=sys.stderr)
        return []
    return [ln for ln in r.stdout.splitlines() if ": error:" in ln]


def scan(include_mypy: bool = False) -> dict[str, list[str]]:
    """Run all checks. Returns {rule id: [finding, ...]}, empty when clean."""
    v: dict[str, list[str]] = defaultdict(list)
    changed = changed_files()
    added_by: dict[Path, set[int]] = {}
    for file in changed:
        added = added_lines(file)
        if not added:
            continue
        added_by[file] = added
        for fn, key in [*rules_code.LINE_RULES, *rules_mojawid.LINE_RULES]:
            for line, msg in fn(file, added):
                v[key].append(f"{_rel(file)}:{line}: {msg}")
    repo_rules = [
        ("file_length", rules_repo.check_file_length(changed)),
        ("function_length", rules_repo.check_function_length(changed, added_by)),
        ("function_caps", rules_repo.check_function_caps(changed, added_by)),
        ("test_layout", rules_repo.check_test_layout(changed)),
        ("tests_for_routes", rules_repo.check_tests_for_routes(changed, added_by)),
        ("alembic_single_head", rules_repo.check_alembic_single_head(changed)),
        ("pyproject", rules_repo.check_pyproject(changed)),
    ]
    for key, findings in repo_rules:
        for path, line, msg in findings:
            where = _rel(path) + (f":{line}" if line else "")
            v[key].append(f"{where}: {msg}" if where else msg)
    if include_mypy:
        v["mypy"].extend(run_mypy(list(added_by)))
    return {k: items for k, items in v.items() if items}


def format_report(v: dict[str, list[str]]) -> str:
    parts: list[str] = []
    for key, header in _HEADERS.items():
        if v.get(key):
            parts += [header + ":", *(f"  - {item}" for item in v[key]), ""]
    return "\n".join(parts).rstrip()


def main() -> int:
    v = scan(include_mypy="--mypy" in sys.argv[1:])
    if not v:
        print("discipline scan: clean")
        return 0
    print(format_report(v))
    return 1


if __name__ == "__main__":
    sys.exit(main())
