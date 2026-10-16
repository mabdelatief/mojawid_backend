# Mojawid API contract

The contract between `mojawid_backend` and `mojawid_flutter`. The machine-readable version is
`openapi.json` next to this file. A test fails if the running API drifts from it, so it changes
only on purpose.

**Status:** draft. Live in dev: health, meta, reference text, reciters, timings. Everything under
"Coming" is the agreed design (`docs/architecture.md`), and may change in detail until it's built.

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
- **Caching:** `/v1/meta` and the reciter responses carry `Cache-Control: public, max-age=3600`.
  Timings change only when they're re-imported. `/v1/reference` is computed per request (fast;
  cache it on the device per selection + settings if you like).

### Error codes

| Status | Code | Meaning |
|---|---|---|
| 400 | `missing_install_id`, `invalid_install_id` | `X-Install-Id` absent or not a UUID |
| 400 | `invalid_text_selection` | The surah/ayah range doesn't exist, or runs backwards |
| 400 | `too_many_ayat` | Over the per-request ayah limit (reference: `limits.max_ayat_manual`, 6; timings: 20) |
| 400 | `invalid_reading_settings` | A reading setting the rules don't allow (e.g. munfasil 2). `details` is empty; the allowed values are in `/v1/meta` |
| 401 | `invalid_api_key` | `X-Api-Key` missing or wrong |
| 404 | `not_found` | No such reciter (or route) |
| 422 | `invalid_request` | A field is missing or malformed. `details` lists which fields, never the submitted values |
| 429 | `rate_limited` | Too many requests. Wait `Retry-After` seconds |
| 500 | `internal_error` | Our bug. Retry later |

More codes come with analyses and reports (below).

## Live now

### `GET /healthz` · `GET /readyz`
Liveness and readiness. No headers needed.

### `GET /v1/meta`
Fetch once at start (it's cached for an hour): everything the app needs before the first
request.

| Field | What it is |
|---|---|
| `reading` | The reading settings a reciter may change: `name`, `label_ar`, `choices` (`value` + `label_ar`; madd lengths come labelled «٤ حركات», «حركتان»), `default`, and `main` (show first; the rest go under «خيارات قراءة أخرى»). Settings the teachers' rulings fix are not listed. Send any of them back as `reading` in `/v1/reference` (and, later, analyses), by `name` → `value` |
| `practices` | Optional practices, all off by default: `{"raum": false}` («أتدرّب على الوقف بالرَّوم») |
| `surahs` | 114 × `{index, name, ayat}` (Arabic names) |
| `limits` | `max_recording_seconds` 60, `soft_recording_seconds` 30 (past this the result carries a warning), `max_upload_bytes` 2 MiB, `max_ayat_manual` 6 |
| `tajweed_classes` | The 7 colour classes, strongest first: `madd6`, `wajib`, `jaiz`, `ghunnah`, `qalqalah`, `tafkheem`, `silent` (the design tokens maddLazim, maddWajib, maddJaiz, ikhfaGhunnah, qalqalah, raaTafkheem, idghamSilent) |
| `engine` | `quran_transcript` and `rules` versions, for bug reports |

### `POST /v1/reference`
The text to show for whole ayat, with its words and tajweed colours. **Always take the Quran text
from here**, never type it or fetch it elsewhere: the colours and the word boundaries must match
what a recording is checked against.

```json
{"sura": 112, "aya_start": 1, "aya_end": 1, "prefixes": ["istiaatha"],
 "reading": {"madd_monfasel_len": 5, "madd_mottasel_len": 5}}
```

- `aya_end - aya_start + 1` ≤ `limits.max_ayat_manual` (6). `prefixes`: any of `istiaatha`,
  `basmala`, said in that order (in al-Fatiha the basmala is ayah 1, so it isn't added again).
  `reading`: optional, by name; unknown names are ignored.

The response, real output for that request:

```json
{
  "uthmani": "أَعُوذُ بِٱللَّهِ مِنَ ٱلشَّيْطَانِ ٱلرَّجِيمِ قُلْ هُوَ ٱللَّهُ أَحَدٌ",
  "segments": [
    {"kind": "istiaatha", "start": 0, "end": 46, "words": []},
    {"kind": "recitation", "start": 47, "end": 71, "words": [
      {"sura": 112, "aya": 1, "word": 0, "start": 47, "end": 51, "ayah_last": false},
      {"sura": 112, "aya": 1, "word": 1, "start": 52, "end": 56, "ayah_last": false},
      {"sura": 112, "aya": 1, "word": 2, "start": 57, "end": 64, "ayah_last": false},
      {"sura": 112, "aya": 1, "word": 3, "start": 65, "end": 71, "ayah_last": true}]}
  ],
  "tajweed": [[10, 12, "silent"], [23, 25, "silent"], [36, 38, "silent"], [38, 41, "tafkheem"],
              [43, 44, "jaiz"], [57, 59, "silent"], [69, 71, "qalqalah"]],
  "classes_present": ["jaiz", "qalqalah", "tafkheem", "silent"]
}
```

- **Positions** are character offsets into `uthmani`, end exclusive.
- **`segments`** are the stretches read without stopping: one per ayah by default, plus a split
  wherever a reading setting says stop (e.g. `sakt_man_raq: "waqf"` splits 75:27). Openings come
  first, with no words.
- **`word`** is the word's index in its ayah, the same index as in the reciter timings. A tap on
  a word plays it from `/v1/reciters/{slug}/timings` with no conversion.
- **`ayah_last`** marks the last word of an ayah: put the ۝ marker after it.
- **`tajweed`**: `[start, end, class]` spans, sorted and non-overlapping; uncoloured text has
  none. Natural (2-count) madd stays plain, as in the printed Mushaf.
- **`classes_present`**: the classes that occur, for dimming the rest of the legend.
- **Colours and mistake marks never appear together** (product rule): «القراءة الصحيحة» shows
  these spans, «ملاحظاتي» shows mistake marks only.

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
1. **Word index:** the word's position in its ayah, 0-based: the `word` of a word in
   `/v1/reference`, unchanged.
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
| `POST /v1/warmup` | 6 | Call when the Record screen opens: wakes the analysis worker (cold start 15–40 s) while the user recites. Returns 202 at once |
| `POST /v1/analyses` | 6 | **Body = the recorded audio file itself** (`Content-Type: audio/*`, ≤ 2 MiB, any common format incl. m4a). Fields go in the query: `client_id` (UUID per attempt), mode, text, openings, reading settings, raum. Returns the result. Idempotent on `client_id`: a resend returns the first result |
| `GET /v1/analyses/{client_id}` | 6 | 200 result / 202 still running / 404. Ask this after a timeout, before re-uploading |
| `POST /v1/reports` + `PUT /v1/reports/{id}/audio` | 7 | Bad-result report. Only with the user's explicit consent (`consent: true`); category, word, note, the result shown, reading settings |

**What the result will carry.** These fields are built and tested in the engine (phase 4); the
endpoint arrives in phase 6. The lab's report fields are listed in `docs/model-and-analysis.md`
§4. New for Mojawid:

- **On every error row:**
  - `sura`, `aya`, `word`: the place, with `word` indexed within the ayah as everywhere else.
    A mistake in an opening has `sura`/`aya` null.
  - `key`: `"{sura}:{aya}:{word}:{error_type}"`, or `"{istiaatha|basmala}:0:{word}:{error_type}"`
    in an opening. It stays the same between attempts, so the app compares the **sets** of keys
    of counted mistakes (fixed / remaining / new). It isn't unique: a word said twice gives the
    same key, which is what the product wants.
  - `mark`, what to draw: `letter` (most serious), `haraka`, `tajweed`, `uncertain` (dotted «؟»),
    or for something that isn't a mistake, `variant` (an allowed way, shown dimmed with its
    reason) or `false_alarm`.
  - `counted`: true only for `letter`, `haraka` and `tajweed`. Uncertain places and allowed
    variants are never counted, and never "worse" between attempts.
  - `expected_harakat` / `heard_harakat`: madd rows only, in harakat. Null for ghunnah, which is
    shown as a state (`ghunnah`: `short`/`long`/`missing`/`izhar`/`unexpected`), never a number.
    The Arabic: «ناقصة» / «زائدة» / «غير موجودة» / «أُظهر الحرف بلا إخفاء» / «غنة في غير موضعها».
    `unexpected` (added 2026-10-16) is a ghunnah held where none is due; its row has
    `error_type: tajweed`.
- **`word_times`:** `[{segment, word, sura, aya, start_s, end_s}]`, each recited word's span in
  the user's own recording, for «استمع لتسجيلي».
  - Play the local copy from `start_s` to `end_s`.
  - A word said again after going back has one entry per recital (its own `segment`).
  - A skipped word, or an opening, has none.
  - Checked against Husary's own word timings: every word found, within 0.3 s.
- **Sifat rows:** each attribute has `allowed`. It's true where the attribute differs but the
  rules count both ways as correct (e.g. the raa of «مِصْرَ» at a stop); show it as correct.
  A row's `tag` follows what was heard on that letter: a letter heard exactly as expected is
  `exact` even when the sifat outputs grouped it differently (2026-10-16).
- **`warnings`:** `[{code, edges, message_ar}]`, with `code` either `cut_in_speech` (`edges`:
  `start` and/or `end`) or `over_30s`.

**Analysis error codes, coming:** `audio_too_large` (413), `audio_unreadable`,
`audio_too_short`, `audio_too_long`, `ayah_not_recognised` (422), `analysis_in_progress`
(409), `analysis_unavailable` (503), `analysis_timeout` (504).
