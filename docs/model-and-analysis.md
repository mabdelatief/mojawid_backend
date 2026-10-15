# The model, and how a recording becomes a result

Mojawid's analysis was worked out in the teachers' lab app **tajweed_ai**
(`~/Documents/GitHub/tajweed_ai`, https://github.com/mabdelatief/tajweed_ai, as of commit
`21b7cf2`, 2026-10-14).
- **tajweed_ai is finished, and it is the reference:** what the analysis must do, the decisions
  behind it, and the reason for each fix.
- **The production backend is rebuilt here,** properly, keeping that behaviour. Mojawid
  features are built in this repo, never added to tajweed_ai.
- This file explains what tajweed_ai does and why. Paths like `muaalem_lab/path.py` are in that
  repo. Its own record of decisions, bugs and measurements is `docs/project-log.md` there;
  section 11 of that file is the latest word.

What the app has to do for the user is in `mojawid_flutter/docs/product.md`.

## 1. The models

### The recitation model
- **`obadx/muaalem-model-v3_2`** (Hugging Face), pinned to snapshot
  `01a1ef9fbe40d144ef845101e89ff924aed3fef5` (`muaalem_lab/model.py`, `MODEL_REVISION`). A new
  upstream revision changes what the model hears, so it is only taken on purpose.
- **What it is:** Wav2Vec2-BERT, 24 layers, hidden size 1024, about 606M parameters. On top
  there are several CTC output heads ("multi-level CTC"). Paper: arXiv 2509.00094.
- **What it takes:** mono audio at 16 kHz. It knows nothing about the expected text. It only
  hears.
- **What it gives:** for every 40 ms frame (25 per second), a probability for each symbol, on
  11 separate outputs:
  - **phonemes:** 43 symbols (0 = "nothing", the CTC blank). These are the letters, harakat
    and the special signs of the phonetic script: madd written as repeated letters, hidden
    noon/meem, qalqalah, sakt, imala, and so on.
  - **10 sifat outputs**, one per letter attribute, with 3–4 values each:

    | Output | Values |
    |---|---|
    | `hams_or_jahr` | همس / جهر |
    | `shidda_or_rakhawa` | شديد / بين الشدة والرخاوة / رخو |
    | `tafkheem_or_taqeeq` | مفخم / مرقق / أدنى المفخم |
    | `itbaq` | مطبق / منفتح |
    | `safeer` | صفير / لا صفير |
    | `qalqla` | مقلقل / لا قلقلة |
    | `tikraar` | مكرر / لا تكرار |
    | `tafashie` | متفشي / لا تفشي |
    | `istitala` | مستطيل / لا إستطالة |
    | `ghonna` | مغن / لا غنة |

    There is **no isti'la/istifal output**. The design's sifat table lists «الاستعلاء/الاستفال»
    as a column, so it has to use these ten (see `product.md`, "Corrections to the design").
- **Lengths are written as repeats.** The model writes a madd of 4 harakat as the madd letter
  4 times, and a held ghunnah as its letter 3 times (4 mid-word after a shadda). A leen madd
  of N harakat is N−1 letters.
- **Running it:**
  - It loads as bfloat16, falling back to float16, then float32.
  - It is not quantized.
  - It uses about 2–3 GB of GPU memory in the running app.
  - Measured on an RTX 4060 laptop GPU: 0.1–0.15 s of model time for 10–30 s of audio, and
    about 1.1 s at worst.
  - One inference at a time per GPU (`LoadedModel.lock`).
- **Training clips were at most 30 s.** The upstream recipe drops longer ones. The lab app
  analyses up to 60 s and warns that accuracy may be lower past 30 s. Recordings of 30–44 s
  have worked well in practice, but this hasn't been measured. Mojawid's 60 s limit is in this
  zone.
- **It can't run live, word by word.** Each frame's output depends on audio about a second
  after it. The structure of the recording (which ayat, where the reciter stopped, where they
  went back) is only known once the recording is complete. The model runs once, on the whole
  recording.

### The pause model
- **`obadx/recitation-segmenter-v2`** (MIT), pinned to `5ee90364e7090ea6eb9dffe80353bed06996a196`
  (`muaalem_lab/pauses.py`). It's the model that cut the recitation model's own training data at
  every pause.
- It labels every 20 ms as speech or silence. It is run in chunks of at most 19.995 s, the
  longest input it was trained on.
- A silence of at least 0.35 s (`MIN_PAUSE_S`) is a pause. It also reports whether the clip
  starts or ends while the reciter is speaking.
- **Known flaw:** it treats a sakt like a stop. The four sakt places are handled separately
  (section 2).

### Packages
- **quran-muaalem 0.2.2** wraps the model. We use its model class and tokenizer, but **not its
  decoding** (section 3). It needs transformers below 5 (its issue #41).
- **quran-transcript 0.6.4** turns Uthmani text into the phonetic script the model writes (the
  "phonetizer"). It also holds the Quran text and an error explainer. tajweed_ai uses **its
  own patched copy** (`vendor/quran-transcript`, `0.6.4+muaalem.1`, patches listed in
  `vendor/quran-transcript/MUAALEM_PATCHES.md`):
  - a stop on «مِنۢ / مَنۢ / عَنۢ …» is a clear noon, not a meem;
  - the «مِصْرَ» and «ٱلْقِطْرِ» raa options work mid-text;
  - «سَلَـٰسِلَا۟» at a stop keeps its alif.

  Over the whole Quran (77,433 stop positions) exactly these places changed and nothing else.
  The Mojawid backend must use this copy, not the PyPI one.
- **Quran text:** Tanzil Uthmani, from inside quran-transcript. It has **no waqf marks**.

## 2. The expected reading

The recording is compared with what a correct recitation of the chosen text sounds like. That
correct version is written in the same phonetic script the model writes.

- **The reading:** Hafs ʿan ʿAsim via al-Shatibiyya, for now. quran-transcript has no Hafs
  preset; `muaalem_lab/quran.py` (`build_moshaf`) sets it.
- **What's correct is decided by the teachers' rulings**, encoded in one place,
  `muaalem_lab/rules.py` (a table per riwaya and tareeq). The rulings came from the user's
  sisters, who are licensed teachers, and **override published sources**. More readings are
  added there as further tables, never as branches in the code. The full table is in the
  tajweed_ai project log (§11.2). The parts that affect a result:
  - **Madd:**
    - munfasil and muttasil are 4/4 by default; 5/5 and 4/5 are also correct;
    - munfasil 2 or 3, or 5 with muttasil 4, is a mistake;
    - a muttasil with the hamza ending the word, at a stop, may be 4, 5 or 6.
    Another allowed length is shown as correct, not as a mistake (`analysis._valid_variant`).
  - **The meem in iqlab and ikhfa shafawi:** lips closed or a slight gap, both correct with the
    ghunnah held.
  - **Raa where both ways are correct:**
    - «وَنُذُرِ» (Al-Qamar) at a stop;
    - «فِرْقٍ» 26:63 when connected (tafkheem only at a stop);
    - «مِصْرَ» at a stop (tafkheem preferred);
    - «ٱلْقِطْرِ» at a stop (tarqeeq preferred).
    Neither way is flagged.
  - **Sakt** at عِوَجَا، مَّرْقَدِنَا، مَنْ رَاقٍ، بَلْ رَانَ: obligatory when connecting; a stop
    instead is allowed; running the words together is a mistake.
  - **«مَالِيَهْ ۜ هَلَكَ»:** a stop, sakt or idgham are all correct. When the reciter connects,
    both are tried and the one heard is kept (`rules.connected_alternatives`).
  - **Raum at a stop:** correct, but only counts when the user has turned on «أتدرّب على الوقف
    بالرَّوم». Otherwise a haraka heard at a stop is a mistake. The teachers asked for this so a
    reciter who doesn't finish the last letter isn't excused. With it on, a damma or kasra at a
    stop shows as «قد يكون رومًا، وهو جائز إن قصدته».
- **Reading settings the user may change** (Settings in the app; the allowed values come from
  `rules.py`, the labels from `quran.moshaf_all_options()`):

  | Setting | Arabic label | Default |
  |---|---|---|
  | `recitation_speed` | سرعة التلاوة | مرتل (also مجود، فويق المرتل، حدر) |
  | `madd_monfasel_len` | مد المنفصل | 4 |
  | `madd_mottasel_len` | مقدار المد المتصل | 4 |
  | `madd_mottasel_waqf` | مقدار المد المتصل وقفا | 4 |
  | `madd_aared_len` | مقدار المد العارض | 4 |
  | `madd_alleen_len` | مقدار مد اللين | 4 |
  | `madd_yaa_alayn_alharfy` | مقدار المد اللازم الحرفي للعين | 6 |
  | `meem_mokhfah` | هل الميم مخفاة أو مدغمة | إخفاء (or ميم) |

- **Openings:** the isti'adha and the basmala are each their own part, ending at a pause.
- **A stretch is phonetized as a whole**, never stitched together from single words. Idgham,
  iqlab, hamzat al-wasl, silah, the 'arid madd and the lam of Allah all depend on the
  neighbouring words (`quran.build_reference_from_structure`). Each stretch ends in a stop.

### Tajweed colours come from the same source
`muaalem_lab/tajweed.py` colours the Uthmani text from the phonetizer output used for the
check: each character's slice of the phonetic script, its madd and qalqalah rules, and the
letters' sifat. It was checked on all 6,236 ayat and takes about 10 ms for 50 ayat. There are
7 classes, and they match the design's legend:

| Class | Design token | Meaning |
|---|---|---|
| `madd6` | maddLazim | madd lazim, 6 counts |
| `wajib` | maddWajib | madd wajib muttasil (also at a stop) |
| `jaiz` | maddJaiz | madd jaiz: munfasil, 'arid, leen |
| `ghunnah` | ikhfaGhunnah | ikhfa and the places of ghunnah |
| `qalqalah` | qalqalah | qalqalah |
| `tafkheem` | raaTafkheem | raa read with tafkheem |
| `silent` | idghamSilent | idgham, and letters not pronounced |

Natural (2-count) madd is left plain, as in the printed Mushaf. The colours always agree with
what the recording is checked against. That is why the app should take them from our API and
not from a third-party tajweed text.

## 3. From audio to result, step by step

This is the order in `POST /api/c/test` (`muaalem_lab/collect_api.py`, `test`).

1. **Read the audio:**
   - ffmpeg converts it to 16 kHz mono;
   - shorter than 0.3 s, or longer than 60 s, is refused;
   - the samples are rounded to 16-bit **before** the model hears them (`_as_saved`), so a
     stored result can be reproduced exactly from the stored file.
2. **Pauses:** the pause model (section 1).
3. **The model:** frame probabilities on all 11 outputs (`decode.frame_probs`).
4. **Our own decoder** (`muaalem_lab/decode.py`) replaces quran-muaalem's, which has three
   faults:
   - it drops a final one-frame letter after a blank;
   - it takes the softmax in bfloat16;
   - it pairs each sifat output with the heard letters by position, so one merged value
     shifts every letter after it, and its fallback writes label ids into the confidences.

   Ours:
   - the heard script is the model's top symbol per frame, repeats merged and blanks dropped
     (greedy CTC), with the edge fixed and the softmax in float32;
   - each sifat output is lined up with the heard letters by order, against each letter's own
     natural value;
   - every heard letter group keeps its frames (`group_frames`), which is where its time in
     the recording comes from;
   - the per-frame probabilities of the phonemes output are kept (`phoneme_probs`), for
     step 9.
5. **Which ayat** (auto mode only, `muaalem_lab/detect.py`):
   - the isti'adha and basmala are found and removed from the start;
   - quran-transcript's `PhoneticSearch` finds where the opening (120, then 240 letters, at 10,
     20, then 30 % tolerance) occurs in the whole Quran;
   - whole-ayah ranges from each start are scored against everything heard;
   - the next ayah is also tried as a start, because a match can begin on the last word of the
     ayah before;
   - when nothing matches, the first half of the opening is searched alone;
   - the closest 4 ranges are scored again by their recitation path (step 6), because a
     reciter who went back to repeat words looks further from the right range than they are
     (`collect_api._choose_range`);
   - the result is the chosen range, whether the choice is clear, and the other close
     candidates ("also matches").
6. **The recitation path** (`muaalem_lab/path.py`): where the reciter stopped, went back or
   joined ayat.
   - A real pause (≥ 0.35 s) **is** a stop. The search never decides "carried on" at a real
     pause, because that would erase a stop on a full haraka.
   - After a stop it decides only where the reciter resumed: the next word, or any earlier word
     back to the start of the previous ayah. There is no fixed number of words, because people
     go back to a place that makes sense as a start.
   - Going back is accepted only when the repeated words are heard again (scored by edit
     distance against each candidate's phonetic script).
   - A short silence (0.15–0.35 s) at an ayah end may or may not be a stop. The better fit
     wins, and the place is marked uncertain.
   - At the sakt places a pause is a stop and no pause is the sakt. At «مَالِيَهْ» the sakt or
     idgham heard is kept.
   - If most of what was heard doesn't match even the best path (more than 30 %), it's another
     text and the plain reading is used.
7. **The expected reading** is rebuilt with that path, so each stop has its stop form (sukoon,
   tanween → alif, 'arid madd, qalqalah, no idgham into the next word).
8. **Comparison** (`muaalem_lab/analysis.py`, `analyze`):
   - quran-transcript's `explain_error` names each difference between the expected and heard
     scripts, with its Uthmani position;
   - our own diff (`phoneme_diff`, never splitting a letter from its haraka) adds the
     differences `explain_error` skips (imala, sakt, mukhtalasa);
   - ghunnah is named by us, because `explain_error` has none (see the row fields below).
9. **How sure the model was** (`muaalem_lab/doubt.py`):
   - for each differing place, it compares how likely the model finds what it heard with how
     likely it finds the expected reading, over that place's frames (CTC likelihood, all
     alignments summed);
   - if the heard reading is under 10× more likely (`DOUBT_RATIO`), the place is
     **uncertain**: shown, not counted as a mistake;
   - the measurement behind 10×: 124 flagged places in 28 recordings; 18 under 10×; none
     between 7.7× and 14×; most at 20× and above;
   - the example that prompted it: the qalqalah of «نُطْعِمُكُمْ» lost to "nothing" by 0.479
     to 0.510 in one frame and showed as a definite mistake;
   - the threshold has to be checked again against teacher-reviewed labels.
10. **Sifat rows:** one row per letter, expected against heard on all 10 attributes.

## 4. The result data, and how it maps to the design

The report (`analyze` → `_result`) holds:

| Field | What it is |
|---|---|
| `uthmani` | The exact Uthmani string that was checked (openings included); every position indexes into it |
| `segments` | The parts recited, in order: `kind` (`istiaatha` / `basmala` / `recitation`), character `start`/`end`, and the words (sura, aya, word index, `ayah_last`). A new segment starts after every stop |
| `words` | Per word: its character start, and runs of characters that share the same set of error ids |
| `tajweed` | `[start, end, class]` spans over `uthmani` (section 2) |
| `reference_phonemes`, `predicted_phonemes` | The expected and heard phonetic scripts |
| `exact_match` | The two scripts are identical |
| `diff` | Blocks of the phonetic diff: `op` (equal / insert / delete / replace), `ref`, `pred` and their spans |
| `errors` | One row per difference (below) |
| `sifat_levels`, `sifat` | The 10 attributes with Arabic names, and one row per letter (`tag` exact / changed / insert / delete; per attribute expected, heard, mismatch) |

Alongside the report it returns `detection` (auto mode: candidates, `clear`, openings heard) and
`warnings`:
- «يبدو أن التسجيل يبدأ/ينتهي أثناء التلاوة؛ قد تكون كلمة مقطوعة، فلا تُحسب خطأً.»
- the clip is over 30 s.

**An error row** has:
- `error_type`: `normal` (a letter), `tashkeel` (a haraka) or `tajweed`;
- `operation`: insert / delete / replace;
- `uthmani_span` / `uthmani_text`: where in the text;
- `word_index`, `segment`;
- `expected_text` / `heard_text`, written for people: plain Arabic with notes such as «مد ٤
  حركات», never the model's own symbols (`muaalem_lab/readable.py`);
- `expected_len` / `predicted_len` (madd, in letters);
- `rules`, with Arabic names;
- `ghunnah`: `short` / `long` / `missing` / `izhar`;
- `likely_false_alarm` + `valid_variant`: the difference is actually correct (an allowed madd
  length, the other meem form, raum with practice on);
- `doubt_ratio` and `uncertain`.

**Mapping to the design's marks** (`design/design_handoff_mojawid/README.md`, Result):

| Design mark | From |
|---|---|
| Wrong letter (most serious) | `error_type: normal` |
| Wrong haraka | `error_type: tashkeel` |
| Tajweed mistake | `error_type: tajweed` (madd length, ghunnah, qalqalah, …) |
| Uncertain («؟», dotted) | `uncertain: true` |
| Stop mid-ayah «وقف» | A segment that ends on a word that isn't `ayah_last`, followed by the next word |
| Stop and repeat «↩» | The next segment starts at or before the last word of this one |
| Corrected since last attempt «✓» | Worked out in the app, between attempts (see `product.md`) |

**What must not be counted as a mistake:**
- rows with `likely_false_alarm` (valid variants, raum with practice on). Today these are
  shown dimmed in the table with their reason, and never in the text;
- `uncertain` rows: shown, never counted, never "worse" between attempts.

**To build here (not in tajweed_ai), needed by the design:**
- **The time span of each word in the user's recording.** It's used only by the «استمع
  لتسجيلي» button in a mistake's bottom sheet. Every other word tap in the app plays the picked
  reciter's word, which comes from the reciter audio (section 7), not from the analysis.
  - Source: the decoder keeps the frames of every heard letter group (`group_frames`, 40 ms
    each). The diff maps heard letters to expected ones, and so to words.
  - A word the user skipped has no span.
- **A stable key per mistake,** for comparing attempts: ayah + word + kind, built from
  `segments` and `word_index`.
- **Mistake rows for the bottom sheet** need the madd count in harakat. `expected_len` /
  `predicted_len` are letters, which is the same number except for leen (letters + 1).

## 5. How the lab app shows a result today

This is `static/review.js`, `screenResult`. Mojawid's design keeps what worked and fixes what
didn't.

- **Summary line:**
  - «التلاوة مطابقة للنص المتوقع.»;
  - or «وُجد N أخطاء، وM مواضع غير مؤكدة (مسطّرة بنقاط).»
  Mojawid rewords this kindly («٣ مواضع للمراجعة…»).
- **Detected ayat** in auto mode, with «وتطابق أيضًا: …» when the choice isn't clear.
- **The marked text.**
  - The problem: the text carried the tajweed colours and the mistake colours at the same
    time, so a tajweed colour could look like a mistake.
  - The design's fix: two views, «ملاحظاتي» (plain text, mistake marks only) and «القراءة
    الصحيحة» (tajweed colours only). The rule: tajweed colours and mistake marks never appear
    together.
  - Mistake severities used different backgrounds per `error_type`; uncertain places a dotted
    underline; stops «وقف», going back «↩».
- **Disclaimer:** «الملاحظات الآلية قد تخطئ ولا تغني عن المعلّم المجاز.» Mojawid keeps it.
- **Phonetic script:** expected and heard side by side, missing / extra / changed coloured;
  tap a block to see «المتوقع … والمسموع …». It becomes "Advanced → المقارنة الصوتية".
- **Mistakes table:** columns place, type («حرف / حركة / تجويد»), change («زيادة / نقص /
  تغيير»), rule, expected, heard, madd count.
  - Valid variants are dimmed with their reason.
  - Uncertain rows say «غير مؤكد: تردد النموذج بين ما سمعه والصواب، فقد تكون القراءة صحيحة».
  - Ghunnah is named as a state («ناقصة / زائدة / غير موجودة / أُظهر الحرف بلا إخفاء»), **never
    a number**: the script's ghunnah run (3 or 4 letters) isn't harakat.
  - It becomes "Advanced → جدول المواضع".
- **Sifat table:** one row per letter, with a filter for letters with a difference. It
  becomes "Advanced → صفات الحروف".
- **Settled wording to keep:**
  - harakat with Arabic number agreement (حركتان, not ٢ حركات);
  - neutral masculine forms;
  - Arabic-Indic digits.

Teacher-only parts (the review, training labels, deliberate mistakes, the prepare screen) are
not part of Mojawid.

## 6. Known limits

- **No waqf marks** in the text, so a bad stop or a bad start isn't detected. The only one
  known is «ٱلِٱسْمُ» 49:11, where starting is a bad start.
- **Raum** is only a flag. The script can't write it, and the model can't tell it from a full
  haraka.
- **The model's weak spots:** ikhfa against a clear noon (paper F1 0.45) and madd length (±1
  haraka). Many of these show as uncertain, not as mistakes.
- **Idgham without ghunnah** (into ل/ر), and izhar where idgham is due, aren't named as
  their own rule (a low-priority open item).
- **The 10× uncertainty threshold** and recognising each pause-to-pause piece separately were
  both measured without teacher-checked labels. Both are to be re-measured once reviews exist
  (tajweed_ai `docs/project-log.md` §11.5). Recognition runs on the whole clip.
- **A candidate improvement for the rebuild: the sifat outputs as a second opinion.** On one
  recording the phonemes output dropped the qalqalah of «نُطْعِمُكُمْ» (0.479 against 0.510),
  while the separate qalqalah output said مقلقل. A place where a sifat output contradicts the
  phonemes output could also be marked uncertain. It's an idea and hasn't been measured; see
  tajweed_ai §11.5.
- **Few voices so far:** all of this was tuned on about 30 recordings from a few reciters, plus
  the Husary clips in the tests. A public app will meet microphones, rooms and voices it hasn't
  seen. The "report a bad result" flow is the way to find these.

## 7. What the backend must provide to the app

These are requirements from the product decisions. The architecture (Modal for the model,
Linode for the Python service, PostgreSQL, docker compose) is still to be discussed.

- **Reference for chosen ayat** (at most 6 per request, see `product.md`):
  - the Uthmani text with ayah ends;
  - tajweed spans;
  - word boundaries (sura, ayah, word index), so each word can be tapped and matched to the
    reciter's word audio;
  - openings when chosen.
  This is the lab's `POST /api/c/reference` plus the spans, and needs no GPU.
- **Analysis of a recording** (≤ 60 s):
  - the steps in section 3 and the result in section 4;
  - plus the mistake key and the user's word spans (section 4, "To build here"). The word
    spans are a separate field, used only for «استمع لتسجيلي»;
  - **the audio is analysed and then discarded, never stored** (product decision);
  - only the GPU step needs Modal; the rest is CPU.
- **Reciters:**
  - the list, offering only reciters with word-by-word audio;
  - ayah audio and word audio (or word timestamps into the ayah audio) for the picked reciter;
  - **every word tap in the app plays this reciter word audio**, the correct word, never the
    user's recording.
  Sources: the quran.com API, everyayah, and the user's own Linode S3, which holds most
  recitations.
- **Bad-result reports:** the audio, the result shown, the reading settings, category, word and
  note, accepted **only with the user's explicit consent**, stored for investigation, and
  **deleted after review**.
- **No accounts.** API keys and rate limiting keep the service safe without getting in a
  normal user's way. Details to be discussed.
- **Idempotent submit:** the lab's `client_id` makes a resent recording return the first
  result instead of running twice. The app's automatic resend after a failed upload needs this.
- **Reading settings** are sent with every request, and the rules table applies the defaults
  and refuses values it doesn't allow.
