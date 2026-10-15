---
name: new-migration
description: |
  Generate and apply an Alembic migration for mojawid_backend the safe way. Use when the user
  says "make a migration", "new migration", "migrate", "autogenerate", "/new-migration", or
  after adding or altering an ORM model. Keeps the single revision chain.
---

# New migration

## GATE — edit or new?

- A migration that exists on `origin/main` may already have run on the production database.
  **Never edit it** (a PreToolUse hook blocks it). Write a NEW revision after the head.
- A revision that is only on your branch may be edited in place.

Mojawid has ONE Alembic chain in `app/db/migrations/versions/`.

> The service, its container and its compose file arrive with the architecture plan. Until then
> run Alembic from `.venv`; once there's a container, run it inside that container so the
> Alembic / SQLAlchemy versions match the app, and update this skill.

## 0. Preconditions

- The model subclasses the one `Base` (`app/db/base.py`) and is imported where Alembic's
  `env.py` collects metadata. A model that isn't imported is invisible to autogenerate.
- Postgres is up.

## 1. Bring the DB to head first

```bash
.venv/bin/alembic upgrade head
.venv/bin/alembic heads   # expect exactly ONE head
```

## 2. Autogenerate

Revision ids are `YYYYMMDD_NNNN` (NNNN = the next sequence number); the file is
`<rev>_<slug>.py`.

```bash
.venv/bin/alembic revision --autogenerate --rev-id <YYYYMMDD_NNNN> -m "<change>"
```

## 3. Review the generated file (REQUIRED)

- `down_revision` is the previous head.
- `upgrade()` touches only the intended tables and columns. A spurious `op.drop_table` means a
  model isn't imported.
- Server defaults, CHECK constraints, indexes and FK names match intent. Autogenerate misses a
  CHECK added to an existing table: add it by hand.
- No column that could hold a recording (`LargeBinary`/`BYTEA`) outside the bad-result reports.
- Data seeds or backfills are written by hand, deliberately, and reviewed.
- Never `ruff format` the versions folder: migrations stay as Alembic generated them.

## 4. Apply and verify

```bash
.venv/bin/alembic upgrade head
.venv/bin/alembic check    # "No new upgrade operations detected."
```

## What this skill does NOT do

Does not commit. Does not edit models; that's where you start before running it.
