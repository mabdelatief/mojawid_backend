# Running Mojawid's backend in dev

Dev runs on this laptop: Postgres in docker compose, and the API on the host through `uv`.
Object storage is the real Linode bucket; there's no local S3. The GPU worker joins in phase 5.
There is no staging; production packaging comes last (`docs/architecture.md`).

## First time

```
docker compose up -d                 # Postgres on :5452
uv sync --extra api                  # API dependencies + dev tools into .venv/
.venv/bin/alembic upgrade head       # the schema
```

Then load the reciters' word timings (`docs/recitations.md`, "In Postgres"):

```
uv run tools/import_timings.py .cache/timings
DATABASE_URL=postgresql://mojawid:mojawid@localhost:5452/mojawid uv run tools/load_timings.py .cache/timings
```

## Every day

```
docker compose up -d
.venv/bin/uvicorn app.main:app --reload --port 8100
```

`http://localhost:8100/docs` shows the API in dev. `/healthz` is liveness and `/readyz` checks
the database. `/v1` routes need `X-Api-Key: mojawid-dev-key` and an `X-Install-Id` UUID. The
contract is `docs/contracts/api.md`; after changing a route, run
`.venv/bin/python -m tools.export_openapi` (a test checks the snapshot).

## Tests

```
.venv/bin/pytest tests/unit -q       # no database, no network
.venv/bin/pytest tests -q            # also tests/db, against a throwaway `mojawid_test` database
```

The DB tests skip, with a reason, when the dev Postgres isn't running. `-m slow` runs the
whole-Quran sweep (every ayah builds a consistent reference, about 25 s). They rebuild
`mojawid_test` from the migrations once per run and roll each test back.

## Goldens: the port against tajweed_ai

`app/engine` is a port of tajweed_ai's `muaalem_lab`, and must keep its behaviour exactly.
`tests/golden/references.json` holds the lab's own output for 216 text selections (every special
boundary place, openings, other reading settings, and seeded random ranges);
`tests/unit/engine/test_text_golden.py` checks the port against it. Regenerate only when the lab
changes on purpose, running in the lab's environment:

```
uv run --project ../tajweed_ai python -m tools.golden.make_text_golden
```

`tests/golden/pipeline/` holds the lab's analysis of 22 Husary cases (single ayat, joined ayat,
an opening, going back, other reading settings, raum, the wrong text) with the model's raw
outputs, made on the GPU by the lab itself. `tests/unit/engine/test_pipeline_golden.py` runs the
port's CPU pipeline on those same outputs and requires the lab's result exactly. Regenerate (lab
environment, GPU; the Husary clips come from our bucket into `.cache/`):

```
HF_HUB_OFFLINE=1 uv run --project ../tajweed_ai python -m tools.golden.make_pipeline_golden
```

The pipeline needs the `worker` extra (torch, transformers, quran-muaalem):
`uv sync --extra api --extra worker`.

## Services

| Service | Address | Credentials (dev only) |
|---|---|---|
| Postgres 17 | `localhost:5452`, db `mojawid` | `mojawid` / `mojawid` |
| Object storage | the real Linode bucket `verseaudiofiles` (eu-central-1), read only | none: the mp3s are public |

Reciter audio is read straight from the bucket. Bad-result report audio (phase 7, the only audio
Mojawid ever stores, and only with consent) will go to a private bucket on the same Linode
Object Storage; it's set up in that phase.

## Migrations

Use `/new-migration`. In short: change the model in `app/db/models/`, then run `.venv/bin/alembic
revision --autogenerate --rev-id <YYYYMMDD_NNNN> -m "<change>"`, review the file, and run
`upgrade head` + `alembic check`. A migration that's on `origin/main` is never edited.
