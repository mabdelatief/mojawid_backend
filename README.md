# mojawid_backend

The backend for **Mojawid (مُجَوِّد)**, a free app with no accounts for practising Quran recitation.
The user recites, and the app shows where the recitation differed from the correct reading.
It will be FastAPI, PostgreSQL and docker compose, with the speech model on Modal. The
architecture is still to be decided; nothing is built yet.

- [`docs/model-and-analysis.md`](docs/model-and-analysis.md): the model, and how a recording
  becomes a result. That work is already done in
  [tajweed_ai](https://github.com/mabdelatief/tajweed_ai). It also lists what the backend must
  provide to the app.
- The product (screens, decisions, privacy) lives in the app repo:
  `mojawid_flutter/docs/product.md`
  ([GitHub](https://github.com/mabdelatief/mojawid_flutter/blob/main/docs/product.md)).
