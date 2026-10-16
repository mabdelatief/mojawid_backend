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

The DB tests skip, with a reason, when the dev Postgres isn't running. They rebuild
`mojawid_test` from the migrations once per run and roll each test back.

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
