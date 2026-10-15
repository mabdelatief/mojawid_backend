# Running Mojawid's backend in dev

Dev runs on this laptop: Postgres and MinIO in docker compose, and the API on the host through
`uv`. The GPU worker joins in phase 5. There is no staging; production packaging comes last
(see the plan in CLAUDE.md "Read first" docs).

## First time

```
docker compose up -d                 # Postgres on :5452, MinIO on :9010 (console :9011)
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
the database.

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
| MinIO (S3) | `localhost:9010`, console `localhost:9011` | `mojawid` / `mojawid-dev-secret` |

The MinIO bucket `mojawid-reports` is private. It will hold bad-result report audio, the only
audio Mojawid ever stores, and only with consent.

## Migrations

Use `/new-migration`. In short: change the model in `app/db/models/`, then run `.venv/bin/alembic
revision --autogenerate --rev-id <YYYYMMDD_NNNN> -m "<change>"`, review the file, and run
`upgrade head` + `alembic check`. A migration that's on `origin/main` is never edited.
