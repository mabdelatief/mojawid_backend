# What we took from upstream, and what we changed (checked 2026-10-16)

Every item was checked against the downloaded upstream artefacts.

| Item | Upstream, version | How we got it | Where | Modified? | Licence; obligations |
|---|---|---|---|---|---|
| **quran-transcript** (phonetizer, rules, Quran text) | github.com/obadx/quran-transcript; PyPI 0.6.4 (sdist sha256 `3d99f3a0…103a`, identical to git tag v0.6.4 `a0417aa3ec`, which is also main) | Vendored copy of the sdist, installed from the path | `vendor/quran-transcript` (identical to tajweed_ai's copy) | **Yes: 2 patches + the version line** (below) | MIT; the LICENSE is kept. Met |
| **quran-muaalem** (model loader, tokenizer, `segment_groups`, Arabic sifat names) | github.com/obadx/quran-muaalem; PyPI 0.2.2 (wheel sha256 `c5b5de2f…`, as in uv.lock) | pip/uv, `worker` extra only | `.venv` | **No.** Byte-identical, no monkeypatching | MIT; nothing owed (not redistributed) |
| recitations-segmenter | github.com/obadx/recitations-segmenter 1.0.0 | **Not installed**; its frame logic re-implemented | `app/engine/pipeline/pauses.py`, `models/segmenter.py` | n/a | MIT; nothing owed |
| **Model** `obadx/muaalem-model-v3_2` | HF revision `01a1ef9fbe40d144ef845101e89ff924aed3fef5` | Downloaded once to the HF cache, loaded offline | `app/model_pins.py` | **No.** All files hash to their blob ids | MIT. **Upstream plans a "controlled licence" and gating (quran-muaalem #46): keep our own copy of these weights and this revision's MIT text** |
| **Model** `obadx/recitation-segmenter-v2` | HF revision `5ee90364e7090ea6eb9dffe80353bed06996a196` | Same | Same | No | MIT |
| Tanzil Uthmani text (v1.1, without pause marks) | tanzil.net, bundled in quran-transcript | Inside the vendored package | `vendor/…/quran-script/` | No | CC-BY 3.0 + Tanzil terms (name and link; don't change the text). **Not met in Mojawid yet: needs credits** |
| Quranic Arabic Corpus morphology 0.4 | corpus.quran.com, bundled | Inside the vendored package | `vendor/…/quranic-corpus-morphology-0.4.txt` | No | GNU GPL + credit. **No code loads it.** Redistributed in our private repos; decide before any public release |
| cpfair/quran-align word timings | release-2016-11-24 | One-time import into Postgres | `recitation_ayah_timing`; the raw zip in the private bucket | Yes, documented (`docs/recitations.md`) | **CC-BY 4.0: attribution required. Not met yet** (`timing_source` is stored but never returned; no credits screen) |
| Reciter audio (9 recitations) | quran.com's per-ayah files | Copied to our bucket | `verseaudiofiles` | No | No licence; risk accepted by the user (2026-10-15) |

## Changes to the vendored quran-transcript (exactly these)

`diff -r` of the PyPI sdist against `vendor/quran-transcript` shows:
1. `pyproject.toml`: `version = "0.6.4"` → `"0.6.4+muaalem.1"`.
2. `src/quran_transcript/phonetics/operations.py` @@ -578: **patch 1**, a noon with the iqlab
   mark at the end of the text becomes a clear sakin noon.
3. `src/quran_transcript/phonetics/sifa.py` @@ -227: **patch 2**, the القطر pattern's hamzat
   al-wasl made optional, and the shadda allowed in «مِّصْرَ».
4. `MUAALEM_PATCHES.md` added.

Nothing else differs: tests, README, LICENSE and all data files are identical. Verdicts on the
two patches are in `phonetizer.md`.

## Re-implemented, not copied

- **Our own code, all ported from the lab:** the forward pass (`models/gpu.py`, fp32 softmax),
  greedy CTC (`ctc.py`), sifat alignment by order (`decode.py`), and the whole analysis
  (`analysis/`).
- **The overlap scan:** a line-by-line comparison against `quran_muaalem`, `quran_transcript` and
  `recitations_segmenter` found only trivial shared lines.
- **Nothing was ever trained or fine-tuned.** The lab only proved the data would train
  (`tools/check_trainable.py`, "no weights change").

## Still owed

1. **A credits text in the app**, which the API can also serve:
   - Tanzil (required);
   - cpfair/quran-align (CC-BY 4.0, required);
   - a courtesy credit to obadx's model and packages.
2. **A LICENSE for mojawid_backend,** if it is ever published.
3. **A decision on the unused GPL morphology file** before any public release.
