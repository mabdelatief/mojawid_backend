# mojawid_backend

The backend for **Mojawid (مُجَوِّد)**, a free Quran recitation practice app with no accounts.
FastAPI and PostgreSQL. The public API (`app/`) will run on a Linode, and the analysis worker
(`app/worker/`) on a Modal Server. In dev everything runs on this laptop: docker compose, plus
the laptop GPU for the worker. The architecture and the build phases were agreed with the user
in `docs/architecture.md`; follow it, and discuss before changing it.

## Read first

1. `docs/architecture.md`: the parts, the privacy rules in code, the API surface, and the build
   phases with their status.
2. `docs/model-and-analysis.md`: the model, how a recording becomes a result, the result data,
   known limits, and what this backend must provide.
3. `../mojawid_flutter/docs/product.md`: the product. It holds the user's decisions, every
   screen, the corrections to the design export, and the open questions.
4. `docs/recitations.md`: the reciters offered, the audio bucket, where the word timings come
   from, and how they're stored.
5. `docs/dev.md`: running it in dev, tests, migrations.
6. `docs/research/README.md`: the 2026-10-16 audit of the model, the wrapper, the phonetizer and
   our engine against the teacher's rulings and al-Shatibiyya. It holds the known defects and the
   fix order. The app accepts exactly what Hafs via al-Shatibiyya allows.

## Rules

- **The analysis was worked out in `../tajweed_ai`** (`muaalem_lab/`, and its
  `docs/project-log.md` §11).
  - tajweed_ai is finished, and it is the reference. Rebuild the analysis here properly, for
    production.
  - Keep its behaviour. Its fixes came from real recordings and the teachers' rulings, and
    each one has a reason recorded there.
  - Never add Mojawid features to tajweed_ai; they're built in this repo.
- **Use tajweed_ai's patched quran-transcript** (`vendor/quran-transcript`,
  `0.6.4+muaalem.1`), never the PyPI release. It changes the expected reading at specific
  places, listed in `MUAALEM_PATCHES.md`.
- **The models stay pinned:**
  - `obadx/muaalem-model-v3_2` at `01a1ef9fbe40d144ef845101e89ff924aed3fef5`;
  - `obadx/recitation-segmenter-v2` at `5ee90364e7090ea6eb9dffe80353bed06996a196`.
  A new revision changes what the model hears, so it is only taken on purpose.
- **Never store a user's recording.** The audio is analysed, then discarded. The one exception
  is a "bad result" report the user explicitly agreed to send. It is kept only to investigate,
  and deleted after review. Logs must not hold audio either.
- **No accounts, no login, no payments.** API keys and rate limits protect the service. They
  must not get in a normal user's way. Details are to be agreed with the user.
- **What is correct tajweed is the teachers' call, not ours.** The user's sisters are licensed
  teachers (Hafs via al-Shatibiyya).
  - Their rulings override published sources, and live in one rules table (tajweed_ai
    `muaalem_lab/rules.py`).
  - When a case isn't covered, ask the user; never guess.
- **A place the model wasn't sure about is never counted as a mistake.** Neither is an
  allowed variant.
- **Nothing third-party at runtime.** Reciter audio comes from our own bucket and word timings
  from our own Postgres; never call quran.com, QUL or the like from the running service. Only
  recitations with word-by-word timing are offered. Pulls from outside sources are one-time
  copies, one request at a time with sleeps (`docs/recitations.md`).

## Code rules

The enforcement layer is in `.claude/`. Every rule below is marked with what enforces it:
- *(scan)*: `.claude/scripts/discipline_scan.py`, which the Stop hook runs on lines added or
  changed vs HEAD;
- *(ruff)*: ruff, run on every edit by the PostToolUse hook and gated by the scan;
- *(mypy)*: mypy, run on the changed files by the Stop hook;
- *(hook)*: a PreToolUse hook;
- *(review)*: judgement only; `/post-pass` asks about it.

The scan blocks the turn until it's clean. Fix the code; never edit a hook or the scanner to get
past it. If a rule seems wrong, say so to the user.

### Python
- **Python 3.12**, the same as tajweed_ai, whose model stack (torch, `transformers<5`) is pinned
  there. Use `uv` and the repo's `.venv/` (`uv sync`), never the host tools.
- Type hints everywhere, `T | None`. Strict typing *(mypy)*. Pydantic v2 and SQLAlchemy 2.0
  only. No `Optional[…]`, `class Config:`, `@validator` or `session.query()` *(scan)*.
- Line length 100, ruff format *(ruff)*.
- **Size caps:** file ≤ 500 lines *(scan)*, function ≤ 60 lines *(scan)*. Complexity ≤ 10, args
  ≤ 6, returns ≤ 6, branches ≤ 12, statements ≤ 50 *(ruff + scan)*. Migrations are exempt.
- **Never `# noqa`, never `# type: ignore`, never a new per-file-ignore** *(scan)*. Split the
  module, extract a collaborator, pass a value object, or fix the type.

### FastAPI
- **Handlers:**
  - every handler is `async def` *(scan)*;
  - a handler is thin: it calls one service method *(review)*;
  - shared logic goes in `Depends`.
- Every route that returns data sets `response_model=` *(scan)*. Every POST/PUT/PATCH/DELETE
  sets an explicit `status_code=` *(scan)*.
- Routers are mounted only in `app/api/router.py` *(scan)*.
- **Errors** go through `AppError` → `{"error": {"code", "message"}}`, never `HTTPException`
  *(scan)*. Never leak internals. Codes are stable, because the app shows its text by code
  *(review)*.
- Long-lived resources (the DB engine, the Modal client) are created in the lifespan.
- **Outside systems only through `app/adapters/`.** That is the only place an HTTP client may
  be imported *(scan)*.

### SQLAlchemy and Postgres
- **One async engine** with `expire_on_commit=False` and `autoflush=False`. **One
  `Base.metadata`**, in `app/db/base.py` *(scan)*.
- Every `relationship()` uses `lazy="raise"`, with explicit `selectinload` where it's needed
  *(scan)*. Never "fix" a `lazy='raise'` error by changing the loading strategy.
- **Repositories never commit or roll back** *(scan)*. Services own the transaction *(review)*.
- **Migrations:**
  - one Alembic chain with a single head, in `app/db/migrations/versions/` *(scan)*;
  - a migration on `origin/main` is never edited: write a new one *(hook)*. Use
    `/new-migration`;
  - never `ruff format` the versions folder.

### Tests
- `tests/unit` (no DB, no network: use fakes), `tests/db`, `tests/integration`. Never flat in
  `tests/` *(scan)*. pytest with `asyncio_mode=auto`.
- A new or changed route ships with a test that calls it *(scan)*.
- The tajweed_ai CPU tests carry over as regression tests for the deterministic parts of the
  analysis.

### Mojawid rules in code
- **Never store a recording** *(scan)*. Outside the bad-result-report code (`…/reports/`),
  none of these is allowed:
  - writing bytes to disk: `open(…, "wb")`, `.write_bytes()`, a temp file with `delete=False`,
    `mkstemp`;
  - a `LargeBinary`/`BYTEA` column;
  - a log call that passes audio, an upload or a request body.

  Decode audio in memory, with ffmpeg through pipes.
- **Nothing third-party at runtime** *(scan)*. HTTP clients only in `app/adapters/`. No URL of
  quran.com, QUL/tarteel, everyayah, quranicaudio, mp3quran, alquran.cloud or tanzil anywhere in
  `app/`. `tools/` (one-time imports) is exempt.
- **Models stay pinned** *(scan)*:
  - model ids and revisions live only in `app/model_pins.py`, which must match the revisions
    above;
  - every `from_pretrained` / `snapshot_download` passes `revision=` from it;
  - changing a revision means changing this file and the scanner's table together, on purpose.
- **Patched quran-transcript only** *(scan)*: `quran-transcript==0.6.4+muaalem.1` from the
  vendored path in `pyproject.toml`, never PyPI.

## Project tracking (Vikunja)

- **Project:** [Mojawid](https://plan.lab.egglink.com/projects/23) (id `23`) — one
  project for the whole product. Every repo in it is a **label**, not a sub-project.
- **Label:** `MJW-BE` (id `35`) — this repo's work inside that project.
- **Use `vk`** (`home-lab/bin/vk`, on PATH) rather than raw MCP calls — it applies the
  label, picks the right bucket and resolves card numbers:
  - `vk queue` — this repo's open work, plus product-wide items that carry no label
  - `vk board` — this repo's blackboard notes
  - `vk note "<title>"` — write a note; it lands in the blackboard bucket, tagged
  - `vk ask <LABEL> "<title>"` — file against another repo; the label is never omitted
  - `vk done <#N> <sha>` — comment the result and hand the card back to whoever asked
  - `vk close <#N>` — finish a card that was handed back to you
  - `vk show <#N>` — resolve a card number, and print its comment thread
- **Sibling labels** in this product:
  - `MJW-APP` (id `36`) — mojawid_flutter
- **A request and its answer are ONE card.** `vk done` posts the result as a comment and moves
  the label to whoever asked. A request crossing to a *different product* needs its own card in
  that product.
- **Buckets on kanban view `97`:** `To-Do` **96** · `Doing` **97** · `Done` **98** ·
  `blackboard` **99**.
- **Blackboard:** bucket `99` holds notes that outlive the session that wrote them — gotchas,
  decisions and their reasons. Knowledge only; a claim on work is a message to the live session
  or a card in `Doing`, never a note.
- **The `#N` on a card is a per-project index, not the task id** — `vk show N` resolves it.
- **Contracts live in git** (`docs/contracts/`), referenced from a card by commit — never pasted
  into the tracker.
