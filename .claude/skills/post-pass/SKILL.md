---
name: post-pass
description: |
  Run the mojawid_backend post-pass checklist before wrapping up work. Use when the user says
  "wrap up", "ready to commit", "post-pass", "final check", or "/post-pass". Reports discipline
  violations and mypy errors on the working-tree diff, eyeballs the rules no scan can check, and
  nudges the docs to update for the area touched. Report-only — never blocks, never commits.
---

# Post-pass checklist

The Stop hook already blocks turn-end on the machine-checked rules. This is the on-demand
version, plus the judgement calls and doc nudges a scan can't do.

## 1. Discipline scan + mypy

```bash
python3 .claude/scripts/discipline_scan.py --mypy
```

It checks lines added or modified vs HEAD under `app/`, `tests/` and `tools/` against the rules
in CLAUDE.md "Code rules" and the Mojawid rules (never store a recording, nothing third-party at
runtime, pinned models, patched quran-transcript). If it reports anything, list it to the user
and stop: it must be fixed before wrap-up. Don't auto-fix unless it's trivial and the user
has okayed auto-fixes for that rule.

## 2. Rules no scan can check — read the diff for these

- **Services own the transaction.** Every write path runs inside the service's transaction;
  repositories only add / flush / select / delete.
- **Handlers are thin.** A route parses, calls one service method and returns. No business
  logic, no DB access in the handler.
- **A recording never outlives the request.** Audio is decoded in memory (ffmpeg via pipes),
  never written to disk, a DB row, a log line, an error message or a metric label. The only
  exception is the bad-result report the user explicitly agreed to send.
- **An uncertain place is never counted as a mistake**, and neither is an allowed variant.
- **Teachers' rulings stay in the one rules table.** No tajweed decision hard-coded elsewhere.
- **Error codes.** New `AppError` codes are intentional and stable: the app shows text by code.

## 3. Doc nudges, by changed path

Ask, as questions, whether these need an update:

| Changed | Doc to consider |
|---|---|
| anything the app can see: a route, request/response field, status or error code | the contract in `docs/contracts/` (shared with mojawid_flutter) |
| the analysis pipeline or the result data | `docs/model-and-analysis.md` |
| reciters, audio, timings, `tools/import_timings.py` | `docs/recitations.md` |
| a new hard rule, or a rule's enforcement | `CLAUDE.md` (and the scanner, together) |

## 4. Optional full sweep (only if the user wants it — slower)

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest tests/unit -q
```

## What this skill does NOT do

Does not commit, push or open PRs. Does not edit docs (it only asks). Does not auto-fix.
