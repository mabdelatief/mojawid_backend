# Reciter audio and word timings

Every word tap in the app plays the picked reciter's word: the correct word, never the user's
recording (model doc §7). So Mojawid offers **only recitations with word-by-word timing**.
This file records where the audio and the timings come from, what was checked, and how they
reach the app. Decided with the user on 2026-10-15.

## Rules

- **Nothing third-party at runtime.** The audio is served from our own bucket and the timings
  from our own Postgres. The app and backend never call quran.com, QUL, everyayah or GitHub, so
  their rate limits and outages can't reach our users.
- **Outside sources are copied once, slowly.** Any pull from someone else's server goes one
  request at a time, with sleeps between requests, and backs off when asked (429 / Retry-After).
- **The timings are keyed to our own words:** the Tanzil Uthmani text from the patched
  quran-transcript, split on spaces. That is what the analysis uses, so a word in a result and a
  word tap point at the same word.

## The recitations offered

All Hafs ʿan ʿAsim, one mp3 per ayah, all 6,236 ayat. Bucket `verseaudiofiles` (Linode,
eu-central-1, `https://verseaudiofiles.eu-central-1.linodeobjects.com/<prefix><SSSAAA>.mp3`).

| Slug | Reciter | Style | Bucket prefix |
|---|---|---|---|
| `abdulbaset-murattal` | عبد الباسط عبد الصمد | murattal | `AbdulBaset/Murattal/mp3/` |
| `sudais` | عبد الرحمن السديس | murattal | `Sudais/mp3/` |
| `shatri` | أبو بكر الشاطري | murattal | `Shatri/mp3/` |
| `rifai` | هاني الرفاعي | murattal | `Rifai/mp3/` |
| `husary` | محمود خليل الحصري | murattal | `Husary_64kbps/` |
| `husary-muallim` | محمود خليل الحصري | muallim | `Husary_Muallim_128kbps/` |
| `minshawi-murattal` | محمد صديق المنشاوي | murattal | `Minshawi/Murattal/mp3/` |
| `shuraym` | سعود الشريم | murattal | `Shuraym/mp3/` |
| `tablawi` | محمد محمود الطبلاوي | murattal | `Mohammad_al_Tablaway_128kbps/` |

**In the bucket but not offered:**
- AbdulBaset Mujawwad (`AbdulBaset/Mujawwad/mp3/`) and Minshawi Mujawwad
  (`Minshawi/Mujawwad/mp3/`): 2.4 % of their words have no timing of their own (merged with a
  neighbour or missing), and they repeat phrases. The audio is kept in case better timings turn
  up.

**Removed:** Alafasy was deleted from the bucket on 2026-10-15 (user's call). The same files
are still on verses.quran.com (`Alafasy/mp3/`).

**Not added for now:** 15 more Hafs recitations with full word timing exist (surah-level files
on QUL / quran.com: al-Dosari, al-Tunaiji, Husary mujawwad, al-Banna, al-Muaiqly, al-Ghamdi and
others). They would be cut into per-ayah files to fit the layout above. Deferred by the user.

## The bucket

- These are quran.com's own per-ayah files, at the same paths and byte-identical on every file
  sampled. That's why quran.com's word timings fit them.
- **Access:**
  - mp3s are public-read;
  - listing the bucket is denied;
  - CORS is `*`;
  - Content-Type is `audio/mpeg` (fixed on 2026-10-15; it was `binary/octet-stream`).
- `timings/` (private) holds:
  - the import output: one `<slug>.json` per recitation, plus `coverage.json`;
  - `timings/raw/`: the source release, exactly as downloaded.

## Where the timings come from

- **Source:** [cpfair/quran-align](https://github.com/cpfair/quran-align), release
  `2016-11-24`, licensed **CC-BY 4.0**. The app's credits must attribute it.
- **It's the same data quran.com serves.** All 9 recitations were compared on 10 surahs (6,930
  ayat) against quran.com's per-ayah segments, and every one was identical. So we hold a
  licensed copy and don't need quran.com's API.
- **How the import changes it** (`tools/import_timings.py`):
  - **Zero-length segments, or ones ending before they start, are dropped.** That word has no
    timing for that reciter (11–43 per recitation).
  - **Off-by-one ayat are shifted back.** In a few ayat that open with separate letters (الٓر،
    الٓمٓر …), cpfair skips an index after the letters, so every later word sits one place too
    far. The segments are shifted back only when that exactly fills the gap. 14 ayat across 6
    recitations; checked against the silences in Husary 12:1 and Husary Muallim 13:1.
  - **Merged spans stay spans.** A tap on any word in one plays the whole span.
- **Coverage after import, out of 77,433 words:**

  | Recitation | Own timing | In a merged span | No timing | Repaired ayat |
  |---|---|---|---|---|
  | husary | 77,384 | 30 | 19 | 12:1, 15:1 |
  | sudais | 77,377 | 23 | 33 | |
  | rifai | 77,362 | 29 | 42 | |
  | minshawi-murattal | 77,348 | 48 | 37 | 10:1, 14:1, 15:1 |
  | shatri | 77,326 | 73 | 34 | 14:1 |
  | shuraym | 77,326 | 8 | 99 (incl. all of 12:76) | |
  | husary-muallim | 77,309 | 88 | 36 | 12:1, 13:1, 14:1, 27:1 |
  | abdulbaset-murattal | 77,285 | 81 | 67 | 11:1, 13:1 |
  | tablawi | 77,157 | 92 | 184 | 10:1, 13:1 |

- **Word numbering differs on quran.com in 4 ayat.** It writes «بَعْدَ مَا» (2:181, 8:6,
  13:37) and «إِلْ يَاسِينَ» (37:130) as one word where Tanzil has two. The cpfair data follows
  Tanzil, so this only matters if quran.com data is ever imported.

## In Postgres

Schema: `tools/sql/recitations.sql`. Loader: `tools/load_timings.py`. Re-running the loader
replaces each recitation's rows, so it's safe to run again.

- **`recitation`** (one row per reciter): slug, Arabic and English names, style, bucket prefix,
  file pattern, timing source, `offered`.
- **`recitation_ayah_timing`** (one row per reciter and ayah, 56,124 rows, about 32 MB):
  `segments` is a 2-D int array of `{first_word, last_word, start_ms, end_ms}` rows. Word
  indexes are 0-based and inclusive; times are in ms into that ayah's mp3.
- **A word tap:** find the segment whose `first_word ≤ word ≤ last_word`, then play that span
  of `bucket_prefix || SSSAAA.mp3`. No segment means the word isn't tappable for this reciter.

To redo the whole thing:

```
uv run tools/import_timings.py OUT_DIR        # downloads the release once into .cache/
DATABASE_URL=postgresql://… uv run tools/load_timings.py OUT_DIR
```

## Licensing

- **Timings:** CC-BY 4.0 (cpfair). The only requirement is attribution: credit
  cpfair/quran-align in the app.
- **Audio: no permission sought; the risk is accepted** (user's decision, 2026-10-15).
  - **Why:** Mojawid is free, with no ads and no income. These recitations are freely available
    and used by many free Quran apps. We serve our own copy and pull nothing from anyone at
    runtime.
  - **What the sources actually say:** none of them publishes the recordings under a licence
    that allows redistribution.
    - Quran Foundation's developer terms (quran.com's owner, updated 2026-10-11) forbid storing
      their content for more than a week.
    - quranicaudio.com says its files are for personal use only.
  - **If a takedown request arrives:** drop that reciter. Its audio and timings are separate
    from the others, so nothing else is affected.
