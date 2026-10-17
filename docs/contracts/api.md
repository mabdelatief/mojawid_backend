# Mojawid API contract

The contract between `mojawid_backend` and `mojawid_flutter`. The machine-readable version is
`openapi.json` next to this file. A test fails if the running API drifts from it, so it changes
only on purpose.

**Status:** draft. Live in dev: health, meta, reference text, reciters, timings, warm-up,
analyses and bad-result reports.

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
| 400 | `consent_required` | A report without `consent: true` |
| 400 | `audio_missing` | A report recording with an empty body |
| 400 | `invalid_reading_settings` | A reading setting the rules don't allow (e.g. munfasil 2). `details` is empty; the allowed values are in `/v1/meta` |
| 401 | `invalid_api_key` | `X-Api-Key` missing or wrong |
| 404 | `not_found` | No such reciter (or route) |
| 404 | `analysis_not_found` | No analysis with this `client_id` for this install (or it's over 24 h old) |
| 404 | `report_not_found` | No such report for this install |
| 404 | `recording_not_found` | No such kept recording (or it was deleted) |
| 400 | `invalid_cursor` | `before` on `/v1/recordings` isn't a `next_before` value |
| 409 | `report_audio_exists` | The report already has its recording |
| 410 | `report_upload_expired` | The recording came over an hour after the report |
| 409 | `analysis_in_progress` | This `client_id` is being analysed right now. Ask `GET /v1/analyses/{client_id}` |
| 413 | `audio_too_large` | The recording is over 2 MiB |
| 422 | `invalid_request` | A field is missing or malformed. `details` lists which fields, never the submitted values |
| 422 | `audio_unreadable`, `audio_too_short`, `audio_too_long`, `ayah_not_recognised`, `no_recitation_heard` | The recording can't give a result (not audio, under 0.3 s, over 60 s, no ayah recognised in auto mode, nothing recited) |
| 429 | `rate_limited` | Too many requests from this install or network. Wait `Retry-After` seconds |
| 500 | `internal_error` | Our bug. Retry later |
| 503 | `analysis_unavailable` | The analysis service didn't come up in time. Send it again shortly (same `client_id`) |
| 503 | `analysis_busy` | Today's analyses for the whole service are used up. Wait `Retry-After` seconds |
| 503 | `reports_unavailable` | Reports can't be received right now. Try again later |
| 504 | `analysis_timeout` | The analysis took too long. Ask `GET /v1/analyses/{client_id}` before sending again |



## Live now

### `GET /healthz` · `GET /readyz`
Liveness and readiness. No headers needed.

### `GET /v1/meta`
Fetch once at start (it's cached for an hour): everything the app needs before the first
request.

| Field | What it is |
|---|---|
| `reading` | The reading settings a reciter may change: `name`, `label_ar`, `choices` (`value` + `label_ar`; madd lengths come labelled «٤ حركات», «حركتان»), `default`, and `main` (show first; the rest go under «خيارات قراءة أخرى»). Settings the teachers' rulings or al-Shatibiyya's text fix are not listed, and a fixed one sent anyway is ignored. Send any of them back as `reading` in `/v1/reference` and analyses, by `name` → `value` |
| `practices` | Optional practices, all off by default: `{"raum": false}` («أتدرّب على الوقف بالرَّوم») |
| `surahs` | 114 × `{index, name, ayat}` (Arabic names) |
| `limits` | `max_recording_seconds` 60, `soft_recording_seconds` 30 (past this the result carries a warning), `max_upload_bytes` 2 MiB, `max_ayat_manual` 6 |
| `tajweed_classes` | The 7 colour classes, strongest first: `madd6`, `wajib`, `jaiz`, `ghunnah`, `qalqalah`, `tafkheem`, `silent` (the design tokens maddLazim, maddWajib, maddJaiz, ikhfaGhunnah, qalqalah, raaTafkheem, idghamSilent) |
| `engine` | `quran_transcript` and `rules` versions, for bug reports |

**Changed 2026-10-16 (data only; the schema is the same).** The settings follow Hafs via
al-Shatibiyya alone; what only al-Tayyiba gives is gone:
- no longer listed (fixed): `noon_and_yaseen` (izhar), `yabsut` and `bastah` (seen), `bimusaytir`
  (saad), `ghonna_lam_and_raa` (none), `saken_before_hamz` (no sakt), `takbeer` (none);
- narrowed: `yalhath_dhalik` and `irkab_maana` to idgham or waqf, `madd_yaa_alayn_alharfy` to 4
  or 6 (default 6). A stored value no longer allowed (e.g. `irkab_maana: izhar`) now gets
  `400 invalid_reading_settings`, so drop saved settings that aren't in the new choices;
- `harakat_daaf`, `noon_tamnna`, `tasheel_or_madd` and `start_with_ism` still offer both ways, but
  the analysis now accepts either way whatever the setting: the setting only picks the way shown.

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
      {"sura": 112, "aya": 1, "word": 0, "start": 47, "end": 51, "ayah_last": false, "waqf": null},
      {"sura": 112, "aya": 1, "word": 1, "start": 52, "end": 56, "ayah_last": false, "waqf": null},
      {"sura": 112, "aya": 1, "word": 2, "start": 57, "end": 64, "ayah_last": false, "waqf": null},
      {"sura": 112, "aya": 1, "word": 3, "start": 65, "end": 71, "ayah_last": true, "waqf": null}]}
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
- **`waqf`** (added 2026-10-17): the Mushaf's waqf signs after the word, as the characters
  themselves, or null. Append them to the word's text **with no space**, so the Quran font
  places them above the word's last letter, as in the printed Mushaf. They aren't in `uthmani`,
  so no offset moves. 4,363 words carry one; one word carries two («مَّرْقَدِنَا» in 36:52: the
  sakt sign, then قلى). They are for display only: where the reciter stopped is never judged
  against them.

  | Char | Sign | Meaning |
  |---|---|---|
  | U+06D6 ۖ | صلى | stopping allowed, continuing better |
  | U+06D7 ۗ | قلى | stopping allowed, stopping better |
  | U+06D8 ۘ | م | stop required |
  | U+06D9 ۙ | لا | don't stop here |
  | U+06DA ۚ | ج | stopping and continuing equal |
  | U+06DB ۛ | ∴ (معانقة) | stop at one of the pair, not both |
  | U+06DC ۜ | س (سكتة) | the sakt (18:1, 36:52, 69:28, 75:27, 83:14) |

  The signs come from Tanzil's text, like the rest of the Quran text. Tanzil's terms ask that the
  app name the source (Tanzil Project) and link to tanzil.net, for example in «عن التطبيق».
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

### `POST /v1/warmup`
Call when the Record screen opens. It always answers at once:
- `200 {"state": "warm"}`: the analysis worker answered moments ago (a warm-up or an analysis
  within the last 4 minutes), so nothing is sent;
- `202 {"state": "warming"}`: it's being woken in the background. In production the worker
  scales to zero and takes 15–40 s to start, so it's ready by the time the recording arrives.

Limits: 20 an hour per install, 60 per network. They'll be revisited once the production worker
exists.

### `POST /v1/analyses`
Analyse one recording.
- **Body:** the recorded audio file itself, as the raw request body (not a form upload),
  ≤ 2 MiB. Any common format: m4a (index at the end is fine), mp3, webm/opus, wav. Set
  `Content-Type` to the file's audio type.
- **Query fields:**

  | Field | Notes |
  |---|---|
  | `client_id` | **Required.** A new UUID for each attempt. Keep it until you have the result |
  | `mode` | `manual` (default) or `auto` |
  | `sura`, `aya_start`, `aya_end` | Manual: the text (`aya_end` defaults to `aya_start`; at most `limits.max_ayat_manual`, 6, ayat). Auto: optional, `sura` + `aya_end` as a hint (the text recited last) |
  | `istiaatha`, `basmala` | `true` when recited before the text (manual mode) |
  | `raum` | `true` when the raum practice is on («أتدرّب على الوقف بالرَّوم») |
  | `reading` | The reading settings as a JSON object, by name → value, as in `/v1/reference` |

- **Returns** `200` with the result (below). Typical time with a warm worker: 1–2 s for 30 s of
  audio.
- **Sending again is safe.** The result is kept for 24 h under (install, `client_id`). Sending
  the same `client_id` again returns the first result without analysing it again, and doesn't
  count against the limits. The same goes for an error that is the recording's own
  (`audio_unreadable`, `ayah_not_recognised`, …): that error comes back again.
- **After a timeout or a dropped connection,** don't upload again straight away. Ask
  `GET /v1/analyses/{client_id}` first, then send again with the **same** `client_id` only if it
  says 404. After `analysis_unavailable` or `analysis_timeout` nothing is kept, so sending again
  runs it.
- **Limits:** 30 analyses an hour and 200 a day per install, 120 an hour per network, and a
  daily total for the whole service (`analysis_busy`).
- **Kept during closed testing** (changed 2026-10-17, the user's decision): the recording is
  analysed in memory, **and** kept on the server with its result and who made it. Every tester
  can list and play it (`/v1/recordings`, below). It's never logged. The response carries
  `X-Recording-Id`, the kept recording's id. **The app must say so before the first recording**
  (consent), and on the Record screen.

### `GET /v1/analyses/{client_id}`
- `200`: the result, as `POST` returned it;
- `202`: `{"status": "running"}`, still being analysed;
- the analysis' own error (e.g. `422 audio_unreadable`);
- `404 analysis_not_found`: unknown, sent by another install, or over 24 h old.

### The result
Top-level fields:
- `mode`: `manual` or `auto`;
- `text`: `sura`, `aya_start`, `aya_end`, `prefixes`, the text it was checked against;
- `duration_s`;
- `summary`: `mistakes` (counted), `uncertain`, `exact_match`;
- `detection`: auto mode's candidates, otherwise null;
- `path`: where the reciter stopped, went back or joined ayat;
- `warnings`;
- `word_times`;
- `report`: the full analysis (`docs/model-and-analysis.md` §4);
- `engine`: the model and rules versions;
- `timings_ms`.

**What's new in the result over the lab's report** (the lab's fields are listed in
`docs/model-and-analysis.md` §4):

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
  - `consistency_ar` (optional, added 2026-10-16): set when a madd length that would be allowed
    on its own is a mistake across the recitation. Either the munfasil and muttasil lengths aren't
    an allowed pair (4/4, 5/5, 4/5), a kind of madd isn't one length throughout (taswiya), or a
    leen is longer than the 'arid. It holds the reason in Arabic; show it with the mistake.
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
  `exact` (2026-10-16). Rows are paired letter by letter, expected against heard (fixed
  2026-10-16, `docs/research/README.md` C1): rows used to pair a letter with its neighbour, and a
  perfect recitation could show a made-up tafkheem mismatch on the lam of «ٱللَّهُ».
- **`warnings`:** `[{code, edges, message_ar}]`, with `code` either `cut_in_speech` (`edges`:
  `start` and/or `end`) or `over_30s`.

### `POST /v1/reports` · `PUT /v1/reports/{id}/audio`
The «نتيجة غير صحيحة؟» flow. Send it **only after the user ticked the consent box**.
1. `POST /v1/reports` with a JSON body (≤ 2 MiB). It returns
   `201 {"id", "upload_audio_until"}`:

   | Field | Notes |
   |---|---|
   | `consent` | **Required, must be `true`** |
   | `category` | `false_mistake` «أشار إلى خطأ لم أقع فيه», `missed_mistake` «لم يلاحظ خطأً وقعت فيه», `wrong_ayat` «تعرّف على آيات غير التي قرأتها», `other` «شيء آخر», or null |
   | `word` | `{sura, aya, word}` (word index within the ayah) or null; filled in from «لم أخطئ هنا؟ أبلغنا» |
   | `note` | Up to 1,000 characters, or null |
   | `analysis_client_id` | The `client_id` of the analysis reported, when there is one |
   | `result` | **Required.** The result the user saw, exactly as `/v1/analyses` returned it |
   | `reading` | The reading settings used |
   | `app_version` | The app's version |

2. `PUT /v1/reports/{id}/audio`: the recording as the raw body (≤ 2 MiB, `Content-Type` set to
   its audio type). It returns `204`. The rules:
   - only from the same install;
   - only once;
   - before `upload_audio_until`, an hour after the report.

- **Limits:** 10 reports a day per install, 30 per network.
- **Privacy:**
  - the recording goes into a private bucket;
  - it's deleted the moment the report is reviewed;
  - the rest of the report is deleted 30 days after review;
  - a report whose recording never arrives is deleted after an hour.

### `GET /v1/recordings` · `GET /v1/recordings/{id}` · `GET /v1/recordings/{id}/audio`
Added 2026-10-17, for closed testing: every recording ever analysed, from every tester, with its
result. Same headers as every `/v1` route.

- **`GET /v1/recordings?limit=&before=`**: newest first, `limit` 1–100 (default 50).
  `{"items": [...], "next_before": "<cursor>" | null}`. For the next page, pass `next_before`
  back as `before`. Each item:

  ```json
  {"id": "…", "client_id": "…", "created_at": "2026-10-17T18:30:00Z", "tester": "m.abdelatief",
   "mode": "manual", "text": {"sura": 112, "aya_start": 1, "aya_end": 4}, "duration_s": 9.4,
   "summary": {"mistakes": 0, "uncertain": 1, "exact_match": false},
   "status": "done", "error_code": null}
  ```

  - `tester`: the part of the tester's login email before «@». It's null for a phone build on the
    Wi-Fi, which has no login.
  - `text`: the detected text in auto mode, otherwise the chosen one.
  - `status`: `running`, `done`, or `failed`. A failed one has `error_code` (for example
    `audio_unreadable`) and no `summary`. Its recording is still kept and playable.
- **`GET /v1/recordings/{id}`**: the same fields, plus `result` (exactly what
  `POST /v1/analyses` returned; open it with the Result screen) and `error_message`.
- **`GET /v1/recordings/{id}/audio`**: the file exactly as it was uploaded, with its
  `Content-Type`. Range requests work. It needs the same headers, so on the web, fetch it with
  them and play the bytes (≤ 2 MiB); an `<audio src>` can't send headers.
- **Who made it** is stored as the install and the login email, so "only my recordings" can come
  later as a filter. Deleting happens only on the admin page.

## Coming

Nothing else is planned for the app's API before production. The admin page (`/admin`) isn't
part of this contract.
