"""Per-line rules for Python, FastAPI and SQLAlchemy code (CLAUDE.md "Code rules").

Each check takes (file, added_lines) and returns [(line, message)] for violations on lines
added or modified vs HEAD only, so existing code is never flagged until it's touched.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from scan_common import (
    APP,
    METADATA_HOME,
    ROUTER_HOMES,
    LineFindings,
    call_name,
    is_migration,
    name_of,
    parse,
    route_decorator,
    under,
)

_SUPPRESSION = re.compile(r"#\s*(noqa\b|type:\s*ignore\b)")


def _app_code(file: Path) -> bool:
    return under(file, APP) and not is_migration(file)


def check_suppressions(file: Path, added: set[int]) -> LineFindings:
    """No new `# noqa` / `# type: ignore` — refactor or fix the type instead."""
    if is_migration(file):
        return []
    try:
        lines = file.read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    return [
        (n, "no new `# noqa` / `# type: ignore` — fix the code or the type instead")
        for n in sorted(added)
        if n <= len(lines) and _SUPPRESSION.search(lines[n - 1])
    ]


def check_lazy_raise(file: Path, added: set[int]) -> LineFindings:
    """Every relationship() declares lazy="raise"."""
    tree = parse(file) if _app_code(file) else None
    if tree is None:
        return []
    out: LineFindings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or call_name(node) != "relationship":
            continue
        lazy = next((kw.value for kw in node.keywords if kw.arg == "lazy"), None)
        ok = isinstance(lazy, ast.Constant) and lazy.value == "raise"
        if not ok and node.lineno in added:
            out.append((node.lineno, 'relationship() must declare lazy="raise"'))
    return out


def check_repo_commit(file: Path, added: set[int]) -> LineFindings:
    """Repositories never commit; services own the transaction."""
    tree = parse(file) if _app_code(file) and "/repositories/" in str(file) else None
    if tree is None:
        return []
    return [
        (node.lineno, "repositories must not commit (services own the transaction)")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"commit", "rollback"}
        and node.lineno in added
    ]


def check_httpexception(file: Path, added: set[int]) -> LineFindings:
    """Errors go through AppError, never HTTPException."""
    tree = parse(file) if _app_code(file) else None
    if tree is None:
        return []
    out: LineFindings = []
    for node in ast.walk(tree):
        hit = (isinstance(node, ast.Call) and call_name(node) == "HTTPException") or (
            isinstance(node, ast.ImportFrom) and any(a.name == "HTTPException" for a in node.names)
        )
        if hit and node.lineno in added:
            out.append((node.lineno, "use AppError, not HTTPException"))
    return out


def _route_handlers(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for dec in node.decorator_list:
                found = route_decorator(dec)
                if found:
                    yield node, dec, found[0], found[1]


def check_route_handlers(file: Path, added: set[int]) -> LineFindings:
    """Handlers are async; mutating routes set status_code=; data routes set response_model=."""
    tree = parse(file) if _app_code(file) else None
    if tree is None:
        return []
    out: LineFindings = []
    for node, dec, verb, call in _route_handlers(tree):
        if dec.lineno not in added and node.lineno not in added:
            continue
        kws = {kw.arg: kw.value for kw in call.keywords} if call else {}
        if isinstance(node, ast.FunctionDef):
            out.append((node.lineno, f"route handler '{node.name}' must be 'async def'"))
        if verb in {"post", "put", "patch", "delete"} and "status_code" not in kws:
            out.append((dec.lineno, f"{verb.upper()} route '{node.name}' must set status_code="))
        no_body = isinstance(kws.get("status_code"), ast.Constant | ast.Attribute) and (
            "204" in ast.unparse(kws["status_code"])
        )
        if (
            verb != "websocket"
            and not no_body
            and not {"response_model", "response_class"} & set(kws)
        ):
            out.append((dec.lineno, f"route '{node.name}' must set response_model="))
    return out


def check_include_router(file: Path, added: set[int]) -> LineFindings:
    """Routers are mounted only in app/api/router.py (and the api router in app/main.py)."""
    if file in ROUTER_HOMES:
        return []
    tree = parse(file) if _app_code(file) else None
    if tree is None:
        return []
    return [
        (node.lineno, "include_router() only in app/api/router.py")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and call_name(node) == "include_router"
        and node.lineno in added
    ]


def check_separate_metadata(file: Path, added: set[int]) -> LineFindings:
    """One Base.metadata — never a second MetaData() or declarative_base()."""
    if file == METADATA_HOME:
        return []
    tree = parse(file) if _app_code(file) else None
    if tree is None:
        return []
    return [
        (node.lineno, "share Base.metadata (app/db/base.py) — no second MetaData()/Base")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and call_name(node) in {"MetaData", "declarative_base"}
        and node.lineno in added
    ]


def _legacy_hit(node: ast.AST) -> str | None:
    if isinstance(node, ast.Subscript) and name_of(node.value) in {"Optional", "Union"}:
        return f"use `T | None` / `A | B`, not {name_of(node.value)}[...]"
    if isinstance(node, ast.ClassDef) and node.name == "Config":
        return "Pydantic v1 `class Config:` — use model_config = ConfigDict(...)"
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        for dec in node.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            if name_of(target) in {"validator", "root_validator"}:
                return "Pydantic v1 validator — use field_validator / model_validator"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        owner = (name_of(node.func.value) or "").lower()
        if node.func.attr == "query" and ("session" in owner or owner == "db"):
            return "SQLAlchemy 1.x session.query() — use select() + session.execute()"
    return None


def check_legacy_patterns(file: Path, added: set[int]) -> LineFindings:
    """No Pydantic v1 / SQLAlchemy 1.x / pre-3.10 typing patterns."""
    tree = parse(file) if _app_code(file) or "/tests/" in str(file) else None
    if tree is None:
        return []
    out: LineFindings = []
    for node in ast.walk(tree):
        msg = _legacy_hit(node)
        if msg and getattr(node, "lineno", 0) in added:
            out.append((node.lineno, msg))
    return out


LINE_RULES = [
    (check_suppressions, "suppressions"),
    (check_lazy_raise, "lazy_raise"),
    (check_repo_commit, "repo_commit"),
    (check_httpexception, "httpexception"),
    (check_route_handlers, "route_handlers"),
    (check_include_router, "include_router"),
    (check_separate_metadata, "separate_metadata"),
    (check_legacy_patterns, "legacy_patterns"),
]
