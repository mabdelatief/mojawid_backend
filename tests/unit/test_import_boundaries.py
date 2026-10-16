"""The API never imports the model stack: no torch, transformers or quran_muaalem, and nothing
from the worker or the engine's pipeline (CLAUDE.md, docs/architecture.md). The API image is
built without them, so an import would only fail in production."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
API_SIDE = ["api", "access", "contracts", "db", "repositories", "services", "engine/text"]
API_SIDE_FILES = ["main.py", "config.py", "errors.py", "log_config.py", "request_context.py"]
FORBIDDEN = ("torch", "transformers", "quran_muaalem", "app.engine.pipeline", "app.worker")


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text())
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def test_api_side_never_imports_the_model_stack() -> None:
    files = [p for d in API_SIDE for p in (APP / d).rglob("*.py")]
    files += [APP / f for f in API_SIDE_FILES]
    bad = [
        f"{p.relative_to(APP)}:{line}: {mod}"
        for p in files
        for line, mod in _imports(p)
        if mod == FORBIDDEN[0] or any(mod == f or mod.startswith(f + ".") for f in FORBIDDEN)
    ]
    assert bad == []


def test_app_starts_without_torch_installed() -> None:
    """Import the API with torch & co. made unimportable, in a fresh interpreter."""
    code = (
        "import sys\n"
        "class Block:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in ('torch', 'transformers', 'quran_muaalem'):\n"
        "            raise ImportError('blocked: ' + name)\n"
        "sys.meta_path.insert(0, Block())\n"
        "import app.main\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=APP.parent, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr[-2000:]
