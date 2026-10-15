"""Shared config and helpers for the discipline scanner (see discipline_scan.py).

Every path the rules care about is in the CONFIG block, so the architecture can move the
service around without touching the rules.
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
from pathlib import Path

# ---------------------------------------------------------------- CONFIG
REPO_ROOT = Path(__file__).resolve().parents[2]
APP = REPO_ROOT / "app"
TESTS = REPO_ROOT / "tests"
TOOLS = REPO_ROOT / "tools"
MIGRATIONS_VERSIONS = APP / "db" / "migrations" / "versions"
ADAPTERS = APP / "adapters"  # the only place allowed to talk to other systems over HTTP
ROUTER_HOMES = (APP / "api" / "router.py", APP / "main.py")  # where routers get mounted
METADATA_HOME = APP / "db" / "base.py"  # the one Base / MetaData
ERRORS_HOME = APP / "errors.py"  # the exception handlers: the one place that catches HTTPException
MODEL_PINS = APP / "model_pins.py"  # the one place model revisions live
PYPROJECT = REPO_ROOT / "pyproject.toml"

SCAN_ROOTS = ("app", "tests", "tools")  # .py files the scanner looks at
LENGTH_ROOTS = ("app", "tests", "tools")  # file-length cap applies here
TEST_DIRS = ("unit", "db", "integration")  # tests/<one of these>/…
ALLOWED_TESTS_ROOT_FILES = {"conftest.py", "__init__.py"}

FILE_CAP = 500
FUNCTION_LINES_CAP = 60
FUNCTION_CAP_CODES = ("C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915")

VENV_BIN = REPO_ROOT / ".venv" / "bin"
# ------------------------------------------------------------------------

LineFindings = list[tuple[int, str]]


def tool_path(name: str) -> str | None:
    """The .venv copy of a dev tool (pinned in pyproject), else the system one."""
    local = VENV_BIN / name
    return str(local) if local.exists() else shutil.which(name)


def run(cmd: list[str], timeout: int = 10) -> str:
    try:
        return subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=timeout
        ).stdout
    except (OSError, subprocess.SubprocessError):
        # git missing, hung or killed — degrade to "no output" so the scan treats the tree as
        # clean rather than crashing the Stop hook.
        return ""


def under(file: Path, root: Path) -> bool:
    return file.is_relative_to(root)


def is_migration(file: Path) -> bool:
    return "/migrations/versions/" in str(file)


def changed_files(suffix: str = ".py") -> list[Path]:
    """Tracked-modified + untracked files under the scan roots (and pyproject.toml)."""
    # --untracked-files=all lists each new file individually; without it git collapses a wholly
    # new directory to the dir path, hiding its files from every check.
    out = run(["git", "status", "--porcelain", "--untracked-files=all", "--", *SCAN_ROOTS])
    files: list[Path] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().split(" -> ")[-1].strip('"')
        p = REPO_ROOT / path
        if path.endswith(suffix) and p.is_file():
            files.append(p)
    return files


def file_changed(rel: str) -> bool:
    return bool(run(["git", "status", "--porcelain", "--", rel]).strip())


def _is_tracked(rel: str) -> bool:
    try:
        rc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
            timeout=10,
        ).returncode
    except (OSError, subprocess.SubprocessError):
        return False  # fail toward checking every line rather than silently skipping
    return rc == 0


def added_lines(file: Path) -> set[int]:
    """Lines added or modified vs HEAD. Untracked files: every line counts as added."""
    rel = str(file.relative_to(REPO_ROOT))
    if not _is_tracked(rel):
        try:
            return set(range(1, len(file.read_text().splitlines()) + 1))
        except (OSError, UnicodeDecodeError):
            return set()
    added: set[int] = set()
    current = 0
    for line in run(["git", "diff", "HEAD", "--unified=0", "--", rel]).splitlines():
        if line.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            current = int(m.group(1)) if m else current
        elif line.startswith(("+++", "---")):
            continue
        elif line.startswith("+"):
            added.add(current)
            current += 1
        elif not line.startswith("-"):
            current += 1
    return added


def parse(file: Path) -> ast.AST | None:
    try:
        return ast.parse(file.read_text())
    except (SyntaxError, UnicodeDecodeError, OSError):
        return None


def name_of(node: ast.AST) -> str | None:
    """Bare name of a Name (`.id`) or Attribute (`.attr`) node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def call_name(node: ast.Call) -> str | None:
    return name_of(node.func)


def route_decorator(dec: ast.expr) -> tuple[str, ast.Call | None] | None:
    """(verb, call) if `dec` is `@router.<verb>(...)` / `@app.<verb>(...)`, else None."""
    target = dec.func if isinstance(dec, ast.Call) else dec
    if not isinstance(target, ast.Attribute):
        return None
    verbs = {"get", "post", "put", "patch", "delete", "websocket", "head", "options"}
    if target.attr not in verbs:
        return None
    owner = name_of(target.value)
    if not owner or ("router" not in owner.lower() and owner != "app"):
        return None
    return target.attr, dec if isinstance(dec, ast.Call) else None


def string_values(value: ast.AST | None) -> list[str]:
    """str constants from a node that is a str, or a tuple/list of strs."""
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return [value.value]
    if isinstance(value, ast.Tuple | ast.List):
        return [
            e.value for e in value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
    return []
