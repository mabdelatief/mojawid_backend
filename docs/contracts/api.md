# Mojawid API contract

The contract between `mojawid_backend` and `mojawid_flutter`. The machine-readable version is
`openapi.json` next to this file. A test fails if the running API drifts from it, so it changes
only on purpose.

**Status:** draft. Live in dev: health, reciters, timings. Everything under "Coming" is the
agreed design (`docs/architecture.md`), and may change in detail until it's built.

## Conventions

- **Base URL:**
  - dev: `http://localhost:8100`;
  - production: `https://api.mojawid.com` (not registered yet).
- **JSON, UTF-8.** Arabic text is returned as-is (Uthmani).
- **Every `/v1` request carries two headers.** There are no accounts:

  | Header | Value |
  |---|---|
  | `X-Api-Key` | The key for the platform build (android / ios / web). Dev: `mojawid-dev-key` |
  | `X-Install-Id` | A random UUID the app generates **once**, on first launch, and keeps. Not tied to the person; the server stores only a keyed hash of it |

- `X-Request-ID` comes back on every response. Send it with bug reports.
- **Errors** always look like this:
  ```json
  {"error": {"code": "too_many_ayat", "message": "At most 20 ayat per request.", "request_id": "…", "details": null}}
  ```
  `code` is stable: **show your own Arabic text by code**, never `message`, which is English
  for developers. On a `429`, `Retry-After` gives the seconds to wait.
- **Caching:** reciter responses carry `Cache-Control: public, max-age=3600`. Timings change
  only when they're re-imported.

### Error codes

| Status | Code | Meaning |
|---|---|---|
| 400 | `missing_install_id`, `invalid_install_id` | `X-Install-Id` absent or not a UUID |
| 400 | `invalid_text_selection` | The surah/ayah range doesn't exist |
| 400 | `too_many_ayat` | Over the per-request ayah limit |
| 401 | `invalid_api_key` | `X-Api-Key` missing or wrong |
| 404 | `not_found` | No such reciter (or route) |
| 422 | `invalid_request` | A field is missing or malformed. `details` lists which fields, never the submitted values |
| 429 | `rate_limited` | Too many requests. Wait `Retry-After` seconds |
| 500 | `internal_error` | Our bug. Retry later |

More codes come with analyses and reports (below).

## Live now

### `GET /healthz` · `GET /readyz`
Liveness and readiness. No headers needed.

### `GET /v1/reciters`
The reciters the app may offer. All of them have word-by-word timings.

```json
{
  "default": "husary",
  "reciters": [
    {"slug": "husary", "name_ar": "محمود خليل الحصري", "name_en": "Mahmoud Khalil al-Husary",
     "style": "murattal",
     "audio_url_template": "https://verseaudiofiles.eu-central-1.linodeobjects.com/Husary_64kbps/{surah:03d}{ayah:03d}.mp3"}
  ]
}
```

- **There are 9 reciters:**
  - AbdulBaset (murattal), Sudais, Shatri, Rifai, Husary, Husary (muallim), Minshawi
    (murattal), Shuraym, Tablawi;
  - `style` is `murattal`, `mujawwad` or `muallim`;
  - two of them share a name (Husary and Husary muallim), so label them by `name_ar` + `style`.
- `audio_url_template`: fill in the surah and ayah, zero-padded to 3 digits (2:255 →
  `002255.mp3`). The files are public mp3s (`audio/mpeg`) in our own bucket. Play them
  directly.

### `GET /v1/reciters/{slug}/timings?surah=&from=&to=`
Where each word is in each ayah's audio, for ayat `from`..`to` of one surah, at most 20 per
request.

```json
{
  "reciter": "husary",
  "ayat": [
    {"surah": 1, "ayah": 1,
     "audio_url": "https://verseaudiofiles.eu-central-1.linodeobjects.com/Husary_64kbps/001001.mp3",
     "segments": [[0, 0, 50, 510], [1, 1, 520, 1180], [2, 2, 1190, 2340], [3, 3, 2350, 4480]]}
  ]
}
```

**Playing a tapped word.** `segments` rows are `[first_word, last_word, start_ms, end_ms]`:
1. **Word index:** the word's position in its ayah, 0-based. Words are the Uthmani text split
   on spaces, the same words `/v1/reference` returns (coming), so a word there maps straight to
   an index here.
2. **Find the segment** with `first_word ≤ index ≤ last_word`, then play `audio_url` from
   `start_ms` to `end_ms`.
3. **A merged span:** a segment covering several words (`first_word < last_word`). A tap on
   any of those words plays the whole span. This is rare: at most 0.3% of words, for any
   reciter.
4. **No segment:** the word isn't tappable for this reciter. That's at most 184 words in the
   whole Quran, for one reciter. Shuraym also has no word timings at all for 12:76.
5. **The ayah marker ۝** plays the whole `audio_url`.

## Coming (agreed design, not built yet)

| Endpoint | Phase | Purpose |
|---|---|---|
| `GET /v1/meta` | 3 | Reading settings (options, defaults, Arabic labels), surahs (name, ayah count), limits (60 s, 6 ayat in manual mode), tajweed classes |
| `POST /v1/reference` | 3 | For a chosen surah + ayat + openings + reading settings: the Uthmani text, segments and words (sura, ayah, word index, character span), tajweed spans and which classes occur |
| `POST /v1/warmup` | 6 | Call when the Record screen opens: wakes the analysis worker (cold start 15–40 s) while the user recites. Returns 202 at once |
| `POST /v1/analyses` | 6 | **Body = the recorded audio file itself** (`Content-Type: audio/*`, ≤ 2 MiB, any common format incl. m4a). Fields go in the query: `client_id` (UUID per attempt), mode, text, openings, reading settings, raum. Returns the result. Idempotent on `client_id`: a resend returns the first result |
| `GET /v1/analyses/{client_id}` | 6 | 200 result / 202 still running / 404. Ask this after a timeout, before re-uploading |
| `POST /v1/reports` + `PUT /v1/reports/{id}/audio` | 7 | Bad-result report. Only with the user's explicit consent (`consent: true`); category, word, note, the result shown, reading settings |

**What the result will carry** (field details in `docs/model-and-analysis.md` §4): the lab
report fields, plus three new ones.
- `word_times`: each word's span in the user's own recording, for «استمع لتسجيلي».
- A stable `key` per mistake (`"{sura}:{aya}:{word}:{error_type}"`), for comparing attempts.
- The madd count in harakat.
- Sifat that differ where both readings are correct are marked `allowed`.

Uncertain places and allowed variants are never counted as mistakes.

**Analysis error codes, coming:** `audio_too_large` (413), `audio_unreadable`,
`audio_too_short`, `audio_too_long`, `ayah_not_recognised` (422), `analysis_in_progress`
(409), `analysis_unavailable` (503), `analysis_timeout` (504).
