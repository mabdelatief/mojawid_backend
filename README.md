# mojawid_backend

The backend for **Mojawid (مُجَوِّد)**, a free app with no accounts for practising Quran recitation.
The user recites, and the app shows where the recitation differed from the correct reading.
FastAPI and PostgreSQL; the speech model runs in a worker on Modal. The plan and its build
phases are in [`docs/architecture.md`](docs/architecture.md).

- [`docs/model-and-analysis.md`](docs/model-and-analysis.md): the model, and how a recording
  becomes a result. That work is already done in
  [tajweed_ai](https://github.com/mabdelatief/tajweed_ai). It also lists what the backend must
  provide to the app.
- [`docs/dev.md`](docs/dev.md): running it in dev (docker compose + uv), tests, migrations.
- [`docs/recitations.md`](docs/recitations.md): the reciters, their audio in our Linode bucket,
  and their word timings (imported once by `tools/`, served from our own Postgres).
- The product (screens, decisions, privacy) lives in the app repo:
  `mojawid_flutter/docs/product.md`
  ([GitHub](https://github.com/mabdelatief/mojawid_flutter/blob/main/docs/product.md)).
