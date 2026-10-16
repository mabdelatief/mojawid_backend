"""File- and repo-level rules: size caps, test layout, tests for routes, migrations, pyproject.

Each takes the changed files (plus added lines where it needs them) and returns findings as
(path_or_None, line_or_None, message).
"""

from __future__ import annotations

import ast
import json
import subprocess
import tomllib
from pathlib import Path

from scan_common import (
    ALLOWED_TESTS_ROOT_FILES,
    APP,
    FILE_CAP,
    FUNCTION_CAP_CODES,
    FUNCTION_LINES_CAP,
    LENGTH_ROOTS,
    MIGRATIONS_VERSIONS,
    PYPROJECT,
    REPO_ROOT,
    TEST_DIRS,
    TESTS,
    file_changed,
    is_migration,
    parse,
    route_decorator,
    run,
    string_values,
    tool_path,
    under,
)

Finding = tuple[Path | None, int | None, str]
QURAN_TRANSCRIPT_PIN = "quran-transcript==0.6.4+muaalem.2"


def _in_length_roots(file: Path) -> bool:
    return any(under(file, REPO_ROOT / r) for r in LENGTH_ROOTS) and not is_migration(file)


def check_file_length(changed: list[Path]) -> list[Finding]:
    """File ≤ FILE_CAP lines. Flags a changed file over the cap — the right time to split it."""
    out: list[Finding] = []
    for file in changed:
        if not _in_length_roots(file):
            continue
        try:
            n = len(file.read_text().splitlines())
        except (OSError, UnicodeDecodeError):
            continue
        if n > FILE_CAP:
            out.append((file, None, f"{n} lines > {FILE_CAP} — split into focused modules"))
    return out


def check_function_length(changed: list[Path], added_by: dict[Path, set[int]]) -> list[Finding]:
    """Function ≤ FUNCTION_LINES_CAP lines (ruff has no rule for this), when its body is touched."""
    out: list[Finding] = []
    for file in changed:
        tree = parse(file) if _in_length_roots(file) else None
        added = added_by.get(file, set())
        if tree is None or not added:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            end = node.end_lineno or node.lineno
            length = end - node.lineno + 1
            if length > FUNCTION_LINES_CAP and not added.isdisjoint(range(node.lineno, end + 1)):
                msg = f"function '{node.name}' is {length} lines > {FUNCTION_LINES_CAP}"
                out.append((file, node.lineno, msg))
    return out


def _function_ends(file: Path) -> dict[int, int]:
    """def-line -> last line, for every function in the file."""
    tree = parse(file)
    return {
        node.lineno: node.end_lineno or node.lineno
        for node in (ast.walk(tree) if tree else [])
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def check_function_caps(changed: list[Path], added_by: dict[Path, set[int]]) -> list[Finding]:
    """Complexity / args / branches / returns / statements caps via ruff, on touched functions."""
    ruff = tool_path("ruff")
    targets = [str(f) for f in changed if _in_length_roots(f)]
    if ruff is None or not targets:
        return []
    cmd = [ruff, "check", "--select", ",".join(FUNCTION_CAP_CODES), "--output-format", "json"]
    try:
        r = subprocess.run(
            [*cmd, *targets], cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=30
        )
        findings = json.loads(r.stdout or "[]")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return []
    out: list[Finding] = []
    for f in findings:
        path = Path(f["filename"]).resolve()
        start = f["location"]["row"]
        # ruff's end_location is the end of the function's *name*, so a change deep in the body
        # would be missed; use the whole function's extent instead.
        end = _function_ends(path).get(start, start)
        if not added_by.get(path, set()).isdisjoint(range(start, end + 1)):
            out.append((path, start, f"{f.get('code')}: {f.get('message')}"))
    return out


def check_test_layout(changed: list[Path]) -> list[Finding]:
    """Tests live under tests/unit, tests/db or tests/integration, never flat in tests/."""
    dirs = ", ".join(f"tests/{d}/" for d in TEST_DIRS)
    return [
        (f, None, f"test files must live under {dirs}")
        for f in changed
        if f.parent == TESTS and f.name not in ALLOWED_TESTS_ROOT_FILES
    ]


def _adds_route(file: Path, added: set[int]) -> bool:
    tree = parse(file) if under(file, APP) else None
    if tree is None:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for dec in node.decorator_list:
                if route_decorator(dec) and (dec.lineno in added or node.lineno in added):
                    return True
    return False


def check_tests_for_routes(changed: list[Path], added_by: dict[Path, set[int]]) -> list[Finding]:
    """A new or changed route ships with a test change."""
    routes = [f for f in changed if _adds_route(f, added_by.get(f, set()))]
    if not routes or any(under(f, TESTS) for f in changed):
        return []
    rels = ", ".join(str(f.relative_to(REPO_ROOT)) for f in routes)
    return [(None, None, f"route(s) added/changed in {rels} but no tests/ file changed")]


def _revision_ids(file: Path) -> tuple[str | None, list[str]]:
    tree = parse(file)
    revision: str | None = None
    downs: list[str] = []
    for node in ast.walk(tree) if tree else []:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name, value = node.target.id, node.value
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
        else:
            continue
        if name == "revision":
            revision = (string_values(value) or [revision])[0]
        elif name == "down_revision":
            downs = string_values(value)
    return revision, downs


def check_alembic_single_head(changed: list[Path]) -> list[Finding]:
    """One Alembic chain: more than one head breaks `alembic upgrade head`."""
    if not any(is_migration(f) for f in changed) or not MIGRATIONS_VERSIONS.exists():
        return []
    revisions: set[str] = set()
    parents: set[str] = set()
    for f in MIGRATIONS_VERSIONS.glob("*.py"):
        rev, downs = _revision_ids(f)
        revisions |= {rev} if rev else set()
        parents |= set(downs)
    heads = sorted(revisions - parents)
    if len(heads) <= 1:
        return []
    return [(None, None, f"multiple Alembic heads: {', '.join(heads)} — add a merge revision")]


def _toml(text: str) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}


def _ignore_keys(data: dict) -> set[str]:
    return set(data.get("tool", {}).get("ruff", {}).get("lint", {}).get("per-file-ignores", {}))


def check_pyproject(changed: list[Path]) -> list[Finding]:
    """No new per-file-ignores; quran-transcript only as the vendored patched copy."""
    if not file_changed("pyproject.toml"):
        return []
    working = _toml(PYPROJECT.read_text())
    head = _toml(run(["git", "show", "HEAD:pyproject.toml"]))
    out: list[Finding] = []
    for key in sorted(_ignore_keys(working) - _ignore_keys(head) if head else set()):
        if not key.endswith("migrations/versions/*.py"):
            out.append((PYPROJECT, None, f"new per-file-ignore {key!r} — refactor to fit caps"))
    deps = list(working.get("project", {}).get("dependencies", []))
    for group in working.get("dependency-groups", {}).values():
        deps += [d for d in group if isinstance(d, str)]
    qt = [d for d in deps if d.replace("_", "-").lower().startswith("quran-transcript")]
    source = working.get("tool", {}).get("uv", {}).get("sources", {}).get("quran-transcript", {})
    for dep in qt:
        if dep.replace(" ", "") != QURAN_TRANSCRIPT_PIN or "path" not in source:
            msg = f"must be {QURAN_TRANSCRIPT_PIN!r} from the vendored path, never PyPI"
            out.append((PYPROJECT, None, f"{dep!r}: {msg}"))
    return out
