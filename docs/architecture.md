# Architecture and build plan

Approved with the user on 2026-10-15. This file is the decision record: what the backend is made
of, why, and the order it's built in. Each phase updates the "Status" line below when it lands.

**Status:** phases 1–4 done: API skeleton, dev compose, recitation tables + timings loaded;
access layer, reciters and timings; `app/engine/text` with `/v1/meta` and `/v1/reference` (216
text goldens match the lab); `app/engine/pipeline`, the CPU side of the analysis (on the lab's
own model outputs it gives exactly the lab's result on 22 Husary cases) plus the new fields
(word times, mistake keys and marks, harakat, allowed sifat). Contract: `docs/contracts/`.

## Context
Mojawid needs a backend that gives the app:
- the reference text with tajweed colours and word boundaries;
- the reciters with their word timings;
- the analysis of a recording;
- bad-result reports.

The analysis already exists in tajweed_ai, the teachers' lab app, which is finished and is the
reference. This plan rebuilds it here for production, keeps its behaviour exactly (proved by
golden tests), and wraps it in a public API. The rules in CLAUDE.md apply throughout, and the
discipline hooks enforce them.

**Scope.** Everything is built and run in dev on this laptop (docker compose, plus the laptop
GPU for the model). There is no staging or UAT. Production packaging (Linode, mojawid.com,
deploy) is the last phase, done only when the user has the server and the domain. The Modal
worker gets wired up before that, once there's a Modal account.

## Architecture

```
Flutter app ──HTTPS──▶ API (app/, FastAPI)  ──Postgres (recitations, idempotency, limits, reports)
   │                     │                  ──private bucket (report audio, Linode Object Storage)
   │                     └─HTTP + token──▶ Worker (app/worker/, FastAPI)
   │                                         dev: laptop GPU · prod: Modal Server (L4, eu)
   └──direct──▶ reciter mp3s in our public bucket (verseaudiofiles)
```

- **The API** runs on CPU and stays light: meta, reference text, reciters and timings,
  analyses (proxied to the worker), warm-up, reports, the admin page, keys and rate limits.
  It never imports torch.
- **The worker** runs the *whole* pipeline: decode → pauses → model → decode → detect → path →
  reference → analysis → doubt → new fields.
  - **In prod it runs inside a Modal "Server".** Modal documents Server request payloads as
    never stored; ordinary function inputs may be kept for up to 7 days.
  - **Cold start** is 15–40 s. The app calls `POST /v1/warmup` when the Record screen opens,
    and recording takes up to 60 s, so the worker is usually warm by the time the audio
    arrives.
  - The API retries on 503 while the container starts.
- **One shared analysis package, `app/engine/`:**
  - `engine/text`: torch-free, used by both the API and the worker;
  - `engine/pipeline`: worker only.
  - It has to sit under `app/`, because the scanner only enforces the Mojawid rules there.

**Privacy.** These rules carry through every phase:
- **Audio travels as the raw request body, never as a form upload.** Starlette writes multipart
  uploads over 1 MiB to a temp file on disk. The body is read into memory with a 2 MiB cap.
- **ffmpeg reads from an in-memory file (Linux `memfd`).** That's RAM only, never disk, so M4A
  files with their index at the end work (user's choice). Output comes back through a pipe.
- **Logs and errors carry only the request id and the error type.** Never a body, a traceback
  with locals, or ffmpeg's stderr.
- **The compressed upload (< 2 MiB) goes to Modal, never decoded PCM.** Modal sends anything
  over 2 MiB through its US object storage.
- **Report audio is the only audio ever stored,** and only with consent: in
  `app/reports/`, in a private bucket. It's deleted the moment a report is marked reviewed;
  the rest of the report goes after 30 days (user's choice).

## Layout

```
app/
  main.py config.py errors.py logging.py model_pins.py
  api/router.py api/deps.py api/body.py api/routes/{health,meta,reference,reciters,analyses,warmup}.py
  contracts/…            wire models shared by API and worker
  services/… repositories/… db/{base,session}.py db/models/… db/migrations/
  adapters/{worker_client,object_store}.py
  reports/{routes,admin_routes,service}.py + admin templates
  engine/text/…          quran_text, moshaf, boundaries, structure, reference, rules, tajweed,
                         readable, groups, letter_sifat, phonetic_diff
  engine/pipeline/…      heard, ctc, decode, pauses, detect, choose_range, doubt, warnings, run,
                         path/{cuts,search,result}, analysis/{rows,missed,words,sifat,marks,report},
                         extras/{word_times,mistake_keys,harakat}, audio, models/{loader,gpu,frame_probs,segmenter}
  worker/{main,auth,service,settings,modal_app}.py
vendor/quran-transcript/   the patched 0.6.4+muaalem.1, copied from tajweed_ai unchanged
docs/contracts/api.md      the contract with mojawid_flutter
```

- **Dependencies:**
  - base: quran-transcript (vendored), numpy, fastapi, pydantic, uvicorn;
  - extra `api`: sqlalchemy async, asyncpg, alembic, httpx, aioboto3, jinja2;
  - extra `worker`: `torch<2.12` (cu128 index), `transformers<5`, `quran-muaalem==0.2.2`;
  - extra `deploy`: modal.
- **An import-boundary test** fails if the API side ever imports torch, quran_muaalem,
  `engine.pipeline` or `worker`.
- **The untyped third-party packages** (quran_transcript, quran_muaalem, diff_match_patch) get a
  mypy `ignore_missing_imports` override in `pyproject.toml`. That's a standard stub setting,
  not a `type: ignore`; their values are wrapped in one typed module.

## Porting tajweed_ai (`muaalem_lab/`)

**Each lab module maps to new, smaller modules,** so every file stays under 500 lines and every
function under 60:
- `quran.py` → 5 files;
- `analysis.py` → `phonetic_diff` plus 6 files;
- `path.py`: its closures become a `PathSearch` class, with tie-breaking kept identical;
- `decode.py` → `ctc` + `decode`;
- `model.py` → `loader` / `gpu`;
- the orchestration of `collect_api /test` → `pipeline/run.py`;
- from `labels.py`, only `ref_groups`, the madd/ghunnah sets and `_letter_sifat` are kept.

**Dropped:** everything teacher-only. That's collect, reviews, drafts, labels and the training
engine, server/static, results, `versions()`, and the `INFER_PATH` flag (path inference is
always on).

**Lab defects fixed in the port:**
- the CPU decoder runs while holding the GPU lock → the lock covers the forward passes only;
- `analyze` runs twice and the reference is built three times per request → once each;
- the idempotency check reads every recording → a Postgres key lookup;
- import cycles → one-way imports: text ← ctc ← decode/doubt ← analysis ← run;
- errors leak internals → `AppError` codes;
- shared objects changed in place → frozen dataclasses;
- `assert` used as a check → explicit checks.

**New result fields** (model doc §4, "To build here"):
- **`word_times`:** each word's span in the user's recording. Heard groups → `group_frames` →
  the diff → reference character → Uthmani word. 40 ms frames, padded by 0.1 s without
  overlapping the neighbouring word. Each repeat after going back is its own entry; a skipped
  word has none.
- **On each error row:** `key` = `"{sura}:{aya}:{word}:{error_type}"`, plus `mark`, `counted`
  and `sura`/`aya`/`word`.
- **`expected_harakat` / `heard_harakat`:** madd rows only, with leen as letters + 1. Never set
  for ghunnah.
- **Allowed sifat** (user's choice): on places where both ways are correct (`rules.both_valid`,
  e.g. the raa of «مِصْرَ»), a sifat attribute that differs carries `allowed: true` and isn't
  shown as a mistake.

## API surface (written up in `docs/contracts/api.md`)

**Headers on every `/v1` route:**
- `X-Api-Key`: one per platform, compared in constant time;
- `X-Install-Id`: a random UUID the app makes on first launch. Only an HMAC of it is stored.
- Rate limits: per install 30 analyses per hour and 200 per day; per IP 120 per hour; plus a
  global daily GPU budget. All configurable.

| Endpoint | Notes |
|---|---|
| `GET /healthz` | no key |
| `GET /v1/meta` | reading settings (options, defaults, Arabic labels), practices, surahs, limits, tajweed classes, engine versions; ETag |
| `POST /v1/reference` | `{sura, aya_start, aya_end, prefixes, reading}` → `uthmani`, `segments` + words, `tajweed` spans, `classes_present` |
| `GET /v1/reciters`, `GET /v1/reciters/{slug}/timings?sura&from&to` | from Postgres; audio URLs point at our bucket |
| `POST /v1/warmup` (202) | wakes the worker; at most one ping per 60 s |
| `POST /v1/analyses` | raw audio body (≤ 2 MiB) plus query fields: `client_id`, mode, text, openings, reading, raum. Idempotent on install + `client_id`; the result is kept 24 h; a replay doesn't count toward the limits |
| `GET /v1/analyses/{client_id}` | 200 result / 202 running / 404 — the app asks this before re-uploading after a timeout |
| `POST /v1/reports` (201) + `PUT /v1/reports/{id}/audio` (204) | `consent: true` required; category, word, note, result, reading |
| `/admin/…` | HTTP Basic with an argon2 hash; list, view, play, "reviewed" |

- **Ayah limit:** at most 6 ayat in manual mode, configurable through `MAX_AYAT_MANUAL`. Auto
  mode is limited only by the 60 s recording (user's choice).
- **Errors:** `{"error": {code, message}}`, with stable codes such as `invalid_api_key`,
  `too_many_ayat`, `audio_too_large`, `audio_unreadable`, `audio_too_short`/`long`,
  `ayah_not_recognised`, `rate_limited`, `analysis_unavailable` and `analysis_timeout`.
- **API → worker:**
  - the worker URL and token come from config;
  - retries on 502/503/504 and on connection errors, for about 90 s in total;
  - it never retries after a read timeout, because the job may already be running.

## Proving the port keeps the lab's behaviour
1. **Port the lab's CPU tests** (structure, rules, tajweed, readable, phonetizer patches,
   analysis, path, detect, decode, doubt) into `tests/unit/engine/`.
2. **Golden outputs from tajweed_ai.**
   - `tools/golden/make_golden.py` runs in tajweed_ai's own environment on Husary clips. Cases:
     1:1, 1:2, 1:3, 1:7, 67:1, 112:1, a joined pair, basmala + ayah, and a go-back. Each runs in
     manual and auto mode, and with other reading settings.
   - The clips are downloaded from our own bucket into `.cache/` at test time and never
     committed.
   - **Private recordings**, the teachers' clips, are optional: read from a path in
     `MOJAWID_PRIVATE_AUDIO_DIR` and never committed.
   - **Text goldens** cover about 200 selections plus every special-boundary place.
3. **Compare at three levels:**
   - **L1:** the port's CPU pipeline on the lab's saved frame probabilities must match the
     lab's report exactly, field by field. This separates porting bugs from GPU noise.
   - **L2:** the full worker on the laptop GPU.
   - **L3:** reference text.

   A difference is investigated, never loosened silently. `word_times` is also checked against
   Husary's own word timings in our DB (about 150 ms tolerance).

## Phases (each one tested and committed on its own)

| # | Builds | Done when |
|---|---|---|
| 1 | **API skeleton + dev compose.** pyproject extras; compose with postgres:17 (no local S3: dev uses the real Linode bucket); `app/{main,config,errors,logging}`, health, db base/session; Alembic async env; migration 0001 for the recitation tables, which replaces `tools/sql/recitations.sql` (deleted); `load_timings.py` needs the migrated schema; `docs/dev.md` | `alembic upgrade head` + `alembic check` report nothing to do; the loader puts **9 recitations and 56,124 rows into the dev DB** (task #8); unit + db tests; scan and mypy clean |
| 2 | **Access layer + reciters + contract draft.** Key, install id and IP deps; rate-limit table (migration 0002, atomic upsert); reciter repo/service/routes; CORS; `docs/contracts/api.md` + OpenAPI snapshot test | 401/400/429 paths tested; 50 concurrent increments give an exact count; timings for 1:1–7 match the import |
| 3 | **Vendored quran-transcript + `engine/text` + meta/reference.** Ported text tests; import-boundary test; text-golden generator | Ported tests pass; L3 matches exactly; 6-ayah reference in under 50 ms when warm |
| 4 | **The pipeline's CPU side.** `engine/pipeline/*` incl. the new fields and allowed sifat; ported pipeline tests; full golden generator | Ported tests pass; **L1 matches exactly** on every Husary case (and the private ones if present); `word_times` within tolerance of the DB timings |
| 5 | **The worker on the laptop GPU.** `model_pins`, models/loader/gpu, memfd audio, raw-body reader, worker app | Worker route tests; GPU tests; **L2 matches**; cold-load and per-request times logged; nothing written to `/tmp` during a request |
| 6 | **API analyses end to end.** Worker adapter, idempotency table (migration 0003), analysis/warm-up services, hourly purge | Retry / timeout / idempotency tests with a fake worker (two concurrent POSTs → one worker call); limits; a dev run end to end, API → local worker |
| 7 | **Reports + admin.** Migration 0004, object-store adapter, a private reports bucket on Linode Object Storage (dev uses it too; created in this phase, with its own access key), report routes, admin page, purge | Integration against the real private bucket: create → upload → view → "reviewed" deletes the audio → the row goes after 30 days |
| 8 | **The worker on Modal** (needs a Modal account). `worker/modal_app.py`: an `@app.server` on an L4 in `eu`, scaling to zero with a ~300 s scaledown, models baked in at the pinned revisions, offline HF; the API switches with `WORKER_URL` | Laptop API → Modal works; cold start measured; warm-up hides it during a 60 s recording; L2 on the L4, with any bf16 differences recorded and discussed |
| 9 | *Deferred until there's a Linode + mojawid.com:* production Dockerfile (API only, no torch), prod compose with TLS, CI, backups, real client IPs behind the proxy | Smoke test on the host; a backup restores |

**Coordination with the app.** When the contract draft lands (phase 2), run `ccwho MJW-APP`.
If a session is live there, message it with the contract commit. If not, propose a `vk ask
MJW-APP` card and wait for the user's yes. No card without it.

## Defaults I'll use unless told otherwise
- `word_times` padding of 0.1 s; the mistake key's "kind" = `error_type` (letter / haraka /
  tajweed).
- An API result of about 200–400 KB for 60 s, mostly sifat rows, sent gzipped.
- Admin access in production (an IP allowlist or a tunnel) is decided in phase 9.

## Verification (overall)
- Each phase ends green on: the Stop hook (scan + mypy), `ruff check`, `pytest tests/unit`,
  `pytest tests/db` (compose Postgres), plus that phase's own check in the table.
- Phase 4 → L1 golden exact; phase 5 → L2 golden on the laptop GPU; phase 6 → a real
  recording through API → worker → result in dev, with no audio in Postgres, logs or `/tmp`.
