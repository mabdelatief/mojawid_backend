#!/usr/bin/env python3
"""PreToolUse Bash blocker.

Refuses bash commands that would stage or commit credential-bearing files: *.key, *.pem, *.pfx,
id_rsa*, any path with `secret`/`credentials` in the name, and `.env` / `.env.*` (Mojawid's hold
real secrets: the API keys, the Modal token, the database password). `.env.example` is a tracked
template and is allowed.

Exit 2 = block (Claude Code surfaces stderr as the reason).
"""

from __future__ import annotations

import json
import re
import sys

_PFX = r"(?:^|[\s/=])"
_SFX = r"(?:\s|$|['\";&|])"
CREDENTIAL_PATTERNS = [
    re.compile(_PFX + r"[^/\s]*\.key" + _SFX),
    re.compile(_PFX + r"[^/\s]*\.pem" + _SFX),
    re.compile(_PFX + r"[^/\s]*\.pfx" + _SFX),
    re.compile(_PFX + r"id_rsa(?:\.[^/\s]+)?" + _SFX),
    re.compile(_PFX + r"[^/\s]*secrets?[^/\s]*\.(?:json|ya?ml|toml|env)" + _SFX),
    re.compile(_PFX + r"[^/\s]*credentials?[^/\s]*\.(?:json|ya?ml|toml)" + _SFX),
    # .env and .env.<anything>, but not .env.example (a tracked template).
    re.compile(_PFX + r"\.env(?!\.example)(?:\.[^/\s]+)?" + _SFX),
]

# git invocations that take file paths as args
GIT_FILE_VERBS = re.compile(r"\bgit\s+(add|commit|stage)\b")


def block(reason: str) -> int:
    print(reason, file=sys.stderr)
    return 2


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0  # malformed input — don't block
    tool = payload.get("tool_name") or payload.get("tool")
    if tool != "Bash":
        return 0
    cmd = (payload.get("tool_input") or {}).get("command", "")
    if not cmd or not GIT_FILE_VERBS.search(cmd):
        return 0
    for pat in CREDENTIAL_PATTERNS:
        m = pat.search(cmd)
        if m:
            return block(
                f"blocked: credential-bearing file in a git command "
                f"(matched {m.group(0).strip()!r}).\n"
                "`.env` and secret/key files must stay out of version control. If a file "
                "genuinely needs tracking, rename it so it doesn't match the credential "
                "patterns, or stage it from a shell outside Claude after manual review."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
