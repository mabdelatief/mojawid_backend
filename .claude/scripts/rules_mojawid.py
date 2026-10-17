"""Mojawid's own rules (CLAUDE.md "Rules"): never store a recording, nothing third-party at
runtime, pinned models. Per-line, on added/modified lines under app/ only (tools/ holds the
one-time imports and is exempt).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from scan_common import (
    ADAPTERS,
    APP,
    MODEL_PINS,
    LineFindings,
    call_name,
    is_migration,
    name_of,
    parse,
    under,
)

# The places allowed to keep a recording: the bad-result reports (with consent), and, while
# Mojawid is in closed testing, every recording (CLAUDE.md, the user's decision 2026-10-17).
_STORING_SEGMENTS = ("/reports/", "/recordings/")

_AUDIO_NAMES = re.compile(r"audio|upload|recording|wave|samples|body|payload", re.IGNORECASE)
_LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}

_HTTP_MODULES = {"httpx", "requests", "aiohttp", "urllib.request", "urllib3"}
_THIRD_PARTY_HOSTS = re.compile(
    r"quran\.com|qurancdn|quran\.foundation|tarteel|everyayah|quranicaudio|mp3quran"
    r"|alquran\.cloud|tanzil\.net",
    re.IGNORECASE,
)

# A new revision changes what the model hears, so it's only taken on purpose: changing one
# means changing CLAUDE.md and this table together.
PINNED_MODELS = {
    "obadx/muaalem-model-v3_2": "01a1ef9fbe40d144ef845101e89ff924aed3fef5",
    "obadx/recitation-segmenter-v2": "5ee90364e7090ea6eb9dffe80353bed06996a196",
}
_MODEL_LOADERS = {"from_pretrained", "snapshot_download", "hf_hub_download"}


def _app_code(file: Path) -> bool:
    return under(file, APP) and not is_migration(file)


def _str_kw(call: ast.Call, name: str, pos: int) -> str | None:
    value = next((kw.value for kw in call.keywords if kw.arg == name), None)
    if value is None and len(call.args) > pos:
        value = call.args[pos]
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None


def _logged_names(node: ast.AST) -> list[str]:
    """Names whose value a log call would print. A size (`len(audio)`) prints no audio."""
    if isinstance(node, ast.Call) and call_name(node) == "len":
        return []
    own = [name_of(node) or ""] if isinstance(node, ast.Name | ast.Attribute) else []
    return own + [n for child in ast.iter_child_nodes(node) for n in _logged_names(child)]


def _http_imports(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        mods = [a.name for a in node.names]
    elif node.module == "urllib":
        mods = [f"urllib.{a.name}" for a in node.names]
    else:
        mods = [node.module or ""]
    return [m for m in mods if m in _HTTP_MODULES or m.split(".")[0] in _HTTP_MODULES]


def _stores_audio(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        name = call_name(node)
        mode = _str_kw(node, "mode", 1) if name == "open" else None
        if mode and "b" in mode and set(mode) & set("wax+"):
            return f'open(..., "{mode}") writes bytes to disk'
        if name == "write_bytes":
            return ".write_bytes() writes bytes to disk"
        if name == "mkstemp" or (
            name == "NamedTemporaryFile"
            and any(kw.arg == "delete" and ast.unparse(kw.value) == "False" for kw in node.keywords)
        ):
            return "a temp file that outlives the request"
        if name in _LOG_METHODS and "log" in (name_of(getattr(node.func, "value", node)) or ""):
            args = [*node.args, *(kw.value for kw in node.keywords)]
            if any(_AUDIO_NAMES.search(n) for a in args for n in _logged_names(a)):
                return "a log call that passes audio / an upload / a request body"
    if isinstance(node, ast.Name | ast.Attribute) and name_of(node) in {"LargeBinary", "BYTEA"}:
        return f"a {name_of(node)} column"
    return None


def check_no_stored_audio(file: Path, added: set[int]) -> LineFindings:
    """Recordings stored only by reports/ and recordings/: no bytes to disk, no binary columns, no
    audio in logs anywhere else."""
    allowed = any(seg in str(file) for seg in _STORING_SEGMENTS)
    tree = parse(file) if _app_code(file) and not allowed else None
    if tree is None:
        return []
    out: LineFindings = []
    for node in ast.walk(tree):
        msg = _stores_audio(node)
        line = getattr(node, "lineno", 0)
        if msg and line in added and (line, msg) not in out:
            out.append((line, f"never store a recording: {msg}"))
    return out


def check_no_third_party(file: Path, added: set[int]) -> LineFindings:
    """HTTP clients only in app/adapters/; no third-party Quran service URLs anywhere in app/."""
    tree = parse(file) if _app_code(file) else None
    if tree is None:
        return []
    in_adapters = under(file, ADAPTERS)
    out: LineFindings = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if line not in added:
            continue
        if isinstance(node, ast.Import | ast.ImportFrom) and not in_adapters:
            for mod in _http_imports(node):
                out.append((line, f"HTTP client {mod!r} outside app/adapters/"))
        is_str = isinstance(node, ast.Constant) and isinstance(node.value, str)
        if is_str and _THIRD_PARTY_HOSTS.search(node.value):
            out.append((line, "no third-party Quran service at runtime (serve from our own)"))
    return out


def check_pinned_models(file: Path, added: set[int]) -> LineFindings:
    """Model ids/revisions live only in app/model_pins.py, which must match PINNED_MODELS;
    every loader call passes revision= by name, never a literal."""
    tree = parse(file) if _app_code(file) else None
    if tree is None:
        return []
    out: LineFindings = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if line not in added:
            continue
        if isinstance(node, ast.Call) and call_name(node) in _MODEL_LOADERS:
            rev = next((kw.value for kw in node.keywords if kw.arg == "revision"), None)
            if not isinstance(rev, ast.Name | ast.Attribute):
                out.append(
                    (line, f"{call_name(node)}() must pass revision= from app/model_pins.py")
                )
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.extend(_pin_literal(file, line, node.value))
    return out


def _pin_literal(file: Path, line: int, text: str) -> LineFindings:
    if text.startswith("obadx/") and file != MODEL_PINS:
        return [(line, "model ids live only in app/model_pins.py")]
    is_revision = file == MODEL_PINS and re.fullmatch(r"[0-9a-f]{40}", text)
    if is_revision and text not in PINNED_MODELS.values():
        return [(line, "new model revision — only on purpose: update CLAUDE.md and the scan")]
    return []


LINE_RULES = [
    (check_no_stored_audio, "no_stored_audio"),
    (check_no_third_party, "no_third_party"),
    (check_pinned_models, "pinned_models"),
]
