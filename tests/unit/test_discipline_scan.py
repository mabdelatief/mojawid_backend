"""Every discipline rule fires on a bad fixture and stays quiet on a clean one.

The rules live in .claude/scripts (agent tooling, run by the hooks on the host python). They
are loaded with importlib and pointed at a temporary app/ tree, so no real code is involved.
"""

from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "scripts"
sys.path.insert(0, str(SCRIPTS))

code: ModuleType = importlib.import_module("rules_code")
mojawid: ModuleType = importlib.import_module("rules_mojawid")
repo: ModuleType = importlib.import_module("rules_repo")

NOQA = "# no" + "qa"  # split so this file doesn't trip the suppression rule itself
TYPE_IGNORE = "# type: " + "ignore"
PIN = "01a1ef9fbe40d144ef845101e89ff924aed3fef5"


@pytest.fixture(autouse=True)
def tmp_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    app = tmp_path / "app"
    for module in (code, mojawid, repo):
        monkeypatch.setattr(module, "APP", app, raising=False)
    monkeypatch.setattr(code, "METADATA_HOME", app / "db" / "base.py")
    monkeypatch.setattr(code, "ERRORS_HOME", app / "errors.py")
    monkeypatch.setattr(code, "ROUTER_HOMES", (app / "api" / "router.py", app / "main.py"))
    monkeypatch.setattr(mojawid, "ADAPTERS", app / "adapters")
    monkeypatch.setattr(mojawid, "MODEL_PINS", app / "model_pins.py")
    monkeypatch.setattr(repo, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(repo, "TESTS", tmp_path / "tests")
    monkeypatch.setattr(repo, "MIGRATIONS_VERSIONS", app / "db" / "migrations" / "versions")
    return tmp_path


def write(root: Path, rel: str, source: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source).lstrip())
    return path


def all_lines(path: Path) -> set[int]:
    return set(range(1, len(path.read_text().splitlines()) + 1))


def run_rule(rule: Any, path: Path) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = rule(path, all_lines(path))
    return findings


ROUTE_OK = """
    @router.post("/x", status_code=201, response_model=Out)
    async def make() -> Out: ...
"""

BAD_LINE_CASES = [
    (code.check_suppressions, "app/a.py", f"x = 1  {NOQA}\n", "noqa"),
    (code.check_suppressions, "tests/unit/t.py", f"y: int = 'a'  {TYPE_IGNORE}\n", "noqa"),
    (code.check_lazy_raise, "app/models/m.py", "r = relationship('X')\n", "lazy"),
    (code.check_repo_commit, "app/repositories/r.py", "await self.s.commit()\n", "commit"),
    (code.check_httpexception, "app/a.py", "raise HTTPException(404)\n", "AppError"),
    (code.check_httpexception, "app/a.py", "from fastapi import HTTPException\n", "AppError"),
    (code.check_httpexception, "app/errors.py", "raise HTTPException(404)\n", "AppError"),
    (code.check_route_handlers, "app/api/a.py", ROUTE_OK.replace("async def", "def"), "async"),
    (
        code.check_route_handlers,
        "app/api/a.py",
        ROUTE_OK.replace("status_code=201, ", ""),
        "status",
    ),
    (
        code.check_route_handlers,
        "app/api/a.py",
        ROUTE_OK.replace(", response_model=Out", ""),
        "model",
    ),
    (code.check_include_router, "app/api/a.py", "app.include_router(r)\n", "router.py"),
    (code.check_separate_metadata, "app/models/m.py", "md = MetaData()\n", "Base.metadata"),
    (code.check_legacy_patterns, "app/a.py", "x: Optional[int] = None\n", "T | None"),
    (code.check_legacy_patterns, "app/a.py", "class M:\n    class Config:\n        pass\n", "v1"),
    (code.check_legacy_patterns, "app/a.py", "@validator('a')\ndef v(c, a): ...\n", "v1"),
    (code.check_legacy_patterns, "app/a.py", "rows = session.query(X).all()\n", "1.x"),
    (mojawid.check_no_stored_audio, "app/a.py", "open(p, 'wb').write(audio)\n", "disk"),
    (mojawid.check_no_stored_audio, "app/a.py", "p.write_bytes(data)\n", "disk"),
    (mojawid.check_no_stored_audio, "app/a.py", "NamedTemporaryFile(delete=False)\n", "temp"),
    (mojawid.check_no_stored_audio, "app/m.py", "c = mapped_column(LargeBinary)\n", "column"),
    (mojawid.check_no_stored_audio, "app/a.py", "logger.info('got %s', audio)\n", "log"),
    (mojawid.check_no_stored_audio, "app/a.py", "log.debug(request.body)\n", "log"),
    (mojawid.check_no_third_party, "app/services/s.py", "import httpx\n", "adapters"),
    (mojawid.check_no_third_party, "app/services/s.py", "from urllib import request\n", "adapters"),
    (mojawid.check_no_third_party, "app/a.py", "U = 'https://api.quran.com/v4'\n", "third-party"),
    (mojawid.check_no_third_party, "app/adapters/x.py", "U = 'https://everyayah.com/'\n", "third"),
    (mojawid.check_pinned_models, "app/m.py", "M.from_pretrained(name)\n", "revision"),
    (mojawid.check_pinned_models, "app/m.py", "M.from_pretrained(n, revision='abc')\n", "revision"),
    (mojawid.check_pinned_models, "app/m.py", "ID = 'obadx/muaalem-model-v3_2'\n", "model_pins"),
    (mojawid.check_pinned_models, "app/model_pins.py", f"R = '{PIN[:-1]}0'\n", "new model"),
]


@pytest.mark.parametrize(("rule", "rel", "source", "expect"), BAD_LINE_CASES)
def test_rule_fires(tmp_tree: Path, rule: Any, rel: str, source: str, expect: str) -> None:
    findings = run_rule(rule, write(tmp_tree, rel, source))
    assert findings, f"{rule.__name__} missed: {source!r}"
    assert any(expect in msg for _, msg in findings), findings


CLEAN = """
from app.adapters.modal import client
from app.model_pins import MUAALEM_REVISION


class Thing(Base):
    items: Mapped[list[Item]] = relationship(lazy="raise")


@router.post("/things", status_code=201, response_model=ThingOut)
async def create(body: ThingIn) -> ThingOut:
    logger.info("analysed %d bytes in %.2f s", len(audio), elapsed)
    with NamedTemporaryFile() as tmp:
        tmp.flush()
    model = M.from_pretrained(MUAALEM_ID, revision=MUAALEM_REVISION)
    x: int | None = None
    raise AppError("not_found", "Not found")


@router.delete("/things/{tid}", status_code=204)
async def remove(tid: int) -> None: ...
"""

LINE_RULES = [rule for rule, _ in code.LINE_RULES + mojawid.LINE_RULES]


@pytest.mark.parametrize("rule", LINE_RULES, ids=lambda r: str(r.__name__))
def test_rule_quiet_on_clean_code(tmp_tree: Path, rule: Any) -> None:
    assert run_rule(rule, write(tmp_tree, "app/api/things.py", CLEAN)) == []


def test_only_added_lines_are_checked(tmp_tree: Path) -> None:
    path = write(tmp_tree, "app/a.py", "raise HTTPException(404)\nx = 1\n")
    assert code.check_httpexception(path, {2}) == []


def test_error_handlers_may_import_httpexception(tmp_tree: Path) -> None:
    source = "from starlette.exceptions import HTTPException as StarletteHTTPException\n"
    path = write(tmp_tree, "app/errors.py", source)
    assert run_rule(code.check_httpexception, path) == []


def test_reports_code_may_keep_a_recording(tmp_tree: Path) -> None:
    path = write(tmp_tree, "app/reports/store.py", "p.write_bytes(data)\n")
    assert run_rule(mojawid.check_no_stored_audio, path) == []


def test_pins_module_may_hold_the_pinned_revision(tmp_tree: Path) -> None:
    path = write(tmp_tree, "app/model_pins.py", f"ID = 'obadx/muaalem-model-v3_2'\nR = '{PIN}'\n")
    assert run_rule(mojawid.check_pinned_models, path) == []


def test_file_and_function_length(tmp_tree: Path) -> None:
    long_file = write(tmp_tree, "app/big.py", "x = 1\n" * 501)
    body = "".join(f"    a{i} = {i}\n" for i in range(61))
    long_fn = write(tmp_tree, "app/fn.py", f"def f() -> None:\n{body}")
    assert repo.check_file_length([long_file, long_fn])[0][0] == long_file
    assert repo.check_function_length([long_fn], {long_fn: {5}})[0][2].startswith("function 'f'")
    assert repo.check_function_length([long_fn], {long_fn: set()}) == []


def test_function_caps_via_ruff(tmp_tree: Path) -> None:
    branches = "".join(f"    if a == {i}:\n        return {i}\n" for i in range(12))
    path = write(tmp_tree, "app/cx.py", f"def f(a: int) -> int:\n{branches}    return -1\n")
    codes = {msg.split(":")[0] for _, _, msg in repo.check_function_caps([path], {path: {3}})}
    assert "C901" in codes


def test_test_layout_and_tests_for_routes(tmp_tree: Path) -> None:
    flat = write(tmp_tree, "tests/test_x.py", "def test_a() -> None: ...\n")
    nested = write(tmp_tree, "tests/unit/test_y.py", "def test_b() -> None: ...\n")
    assert repo.check_test_layout([flat, nested]) == [
        (flat, None, repo.check_test_layout([flat])[0][2])
    ]
    route = write(tmp_tree, "app/api/r.py", ROUTE_OK)
    added = {route: all_lines(route)}
    assert repo.check_tests_for_routes([route], added)
    assert repo.check_tests_for_routes([route, nested], added) == []


def test_alembic_single_head(tmp_tree: Path) -> None:
    versions = "app/db/migrations/versions"
    write(tmp_tree, f"{versions}/a.py", "revision = 'a'\ndown_revision = None\n")
    b = write(tmp_tree, f"{versions}/b.py", "revision = 'b'\ndown_revision = 'a'\n")
    assert repo.check_alembic_single_head([b]) == []
    c = write(tmp_tree, f"{versions}/c.py", "revision = 'c'\ndown_revision = 'a'\n")
    assert "multiple Alembic heads" in repo.check_alembic_single_head([c])[0][2]


def _pyproject(tmp: Path, monkeypatch: pytest.MonkeyPatch, head: str, working: str) -> Any:
    path = write(tmp, "pyproject.toml", working)
    monkeypatch.setattr(repo, "PYPROJECT", path)
    monkeypatch.setattr(repo, "file_changed", lambda rel: True)
    monkeypatch.setattr(repo, "run", lambda cmd: head)
    return repo.check_pyproject([])


def test_pyproject_rules(tmp_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    head = '[tool.ruff.lint.per-file-ignores]\n"app/db/migrations/versions/*.py" = ["E501"]\n'
    grown = head + '"app/big.py" = ["C901"]\n'
    assert "per-file-ignore" in _pyproject(tmp_tree, monkeypatch, head, grown)[0][2]
    pypi = '[project]\ndependencies = ["quran-transcript==0.6.4"]\n'
    assert "vendored" in _pyproject(tmp_tree, monkeypatch, "", pypi)[0][2]
    vendored = (
        '[project]\ndependencies = ["quran-transcript==0.6.4+muaalem.2"]\n'
        '[tool.uv.sources]\nquran-transcript = { path = "vendor/quran-transcript" }\n'
    )
    assert _pyproject(tmp_tree, monkeypatch, "", vendored) == []
