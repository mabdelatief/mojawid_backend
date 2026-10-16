# What others have built and found with the model (checked 2026-10-16)

## The HF Community threads and the تسميع findings

The model's Community tab has three threads (2026-08-13 and 08-22), all by **omar-abu-hfs-siraj**
(Omar al-Solaybi, Mushaf al-Siraj); the model's author replied.

He built a **تسميع** tool on the model. It checks obvious mistakes (اللحن الجلي) only: words,
letters, shadda and harakat, dropped, added or changed. Tajweed is left out on purpose. The
principle is "the machine suggests, the teacher confirms".

Findings repo: `huggingface.co/datasets/omar-abu-hfs-siraj/tasmee3-muaalem-findings`, which has
code, a 19-chapter method document and raw outputs. A newer GitHub mirror exists:
`github.com/omarhfs34-ops/tasmee3-muaalem-findings`, pushed 2026-10-09.

**What he measured.** Almost all of it is his own voice, made on purpose: about 40–50
recordings, 9 with saved outputs, no statistics computed.

| Item | Result |
|---|---|
| Wrong haraka on a word | 6/6 written as spoken; the basmala pair found and placed |
| Dropped word | Its letters vanish from the heard script; his locator ("best-drop": `|R| − LCS(R,S)`, then the word whose removal best explains it) got 7/7 on 2 ayat |
| **Letter change** | Caught 2/5, later stated 3/7, latest 3/9 (Itqan `/d/834`); ف→ج missed; the cause is unsettled |
| Dropped shadda | Found 3/3, but it put a false "dropped word" on the neighbour until he added a rule |
| Dropped natural madd (قَالَا → قَالَ) | The model hears it; his tajweed filter hid it until he changed the filter |
| False alarms | Breath «ه» at the end; background noise as insertions; stops; a false letter change on a neighbouring word in 3/3 recordings of al-Fil 1 |
| Upstream `/correct-recitation` | Correct readings 3/3 clean; mistakes: 3 of 4 return 500 (`No results found. Try increasing error_ratio`): the ayah search fails when a word is dropped |
| Speed (2011 CPU, no AVX2) | bf16 102.7 s, fp32 22.9 s, ONNX fp32 ~8 s for one basmala, same output. The accuracy comparison is about one clip |

**Against our engine.**
- **Dropped shadda → false word on the neighbour:** not exposed. That artefact comes from his
  locator, which we don't have.
- **Word skipped → the comparison slides onto the next word:** **exposed**
  (`wrapper-and-engine.md`). His best-drop idea is the fix to consider.
- **Letter changes under-detected:** the same model, so the same limit. It is a learned prior, not
  reference forcing: the phonemes output never sees the reference.
- **His false-alarm rules:** nothing to copy. Our stop-aware reference and the doubt ratio do
  this better.
- **Breath:** still to be measured on our stored recordings.
- **For تسميع later:** start from a known point (never search the whole Quran per recording);
  collapse per-letter deletions into "word skipped"; label inserts as "between words" vs "inside
  a word"; treat letter changes as weak evidence; borrow his wording «لا أخطاء جلية فيما سُمع»
  ("no obvious mistakes in what was heard") in place of "correct".
- **His code:** no code worth reusing. The repo calls itself صدقة جارية ("free to build on") but
  has no licence field. Credit him if we use his ideas.

## Links from those threads

- **Al-Muqri / المقرئ** (`github.com/nandxorandor/al-muqri`, MIT; Android, Windows, Linux).
  - **How it uses the model:** phonemes only, as int8 ONNX in a 4 s window. It matches only
    against the open page or ayah, never a whole-Quran search.
  - **How it judges:** a per-word edit distance with thresholds (`passRate` 0.25, `harakaDrop` 2,
    `maddLimit` 1, strict vowel and letter checks).
  - **Edge correction:** it phonetizes each word alone to fix the two outer edges of a partial
    clip.
  - **What it forgives at the edges:** a leading hamza or vowel, and the last vowel or madd.
    Never a consonant.
  - **A rejection gate** for recordings that don't match (cost 0.35, margin 0.12, minimum 12
    phonemes).
  - **Worth considering for us:** the edge correction and the rejection gate.
  - It calls QUL/Tarteel at runtime, which our rules forbid.
- **Itqan / إتقان** (`community.itqan.dev`), a Quran-tech developers' community.
  - The claim that the model's author explained errors leaking onto neighbouring words **could
    not be found**; treat it as unverified.
  - What the author *did* say (quran-muaalem #39): the reference assumes the clip starts at its
    first word and stops at its last, and very short clips («قل») do poorly.
  - In `/d/584` he wrote **«الأداء الحالي للنماذج غير كافي»** ("the current models' performance
    is not sufficient"), and that recordings of skilled reciters need labelling.
- **Zulfa / زلفى:** a teacher-led app with no recitation model; a human grades each clip. Only its
  "listen to the ayah, then record" flow is relevant.
- **His profile:** two datasets only (the findings, and unrelated quizzes).

## Upstream state and the rest of the ecosystem

- **No newer model.** `muaalem-model-v3_2` HEAD is still our pin (2025-09-04).
  - The 2026 "mini", w2v2-384, whisper-encoder and streaming repos are placeholders with no
    weights.
  - `muaalem-v3_2-torchscript` is an export of the same weights.
  - The planned `muaalem-fastconformer` has phonemes only, no sifat, so it can't replace v3_2 for
    us.
  - `recitation-segmenter-v2` HEAD is our pin.
- **No newer package to take.** quran-transcript 0.6.4 is the latest tag. The unreleased branch
  `feat-18-noon-rules` touches `operations.py` and `sifa.py`; run the whole-Quran diff before
  ever taking it. quran-muaalem 0.2.2 is the latest.
- **Licence risk.** The upstream roadmap (quran-muaalem #46) lists "update Muaalem to the new
  controlled license" and "make the model gated". Our pin is the MIT revision. **Keep our own
  copy of the v3_2 weights and that revision's MIT text.**
- **Confirmed upstream and still unfixed:** the decode `new_probs` bug (#6); the doubled raa at a
  stop and the idgham-naqis qalqalah (both still in 0.6.4, with no issue).
  - **Not reported by anyone:** the sifat pairing bug in `merge_same_phoneme_group`.
- **Training labels vs the phonetizer:** quran-muaalem #45 (`paper.md`). Nine ayah-end stops
  were trained with an alif where the reading is ha. Candidates for golden tests and an "unsure"
  rule.
- **Madd length in the training labels is fixed per reciter.** A Quran-Lab audit found 97.4% of
  them follow the recitation's configured length. So the model tends to *write* the expected
  length, not the length it heard. Madd-length mistakes judged from the model's run length are
  therefore weak evidence. The paper's learner RMSE (0.46–1.03 harakat) shows it does hear some
  of it, but not reliably.
- **Limits upstream itself states:** weak on a single short word such as «قل» (#39); over-fits
  the start of each surah and al-Fatiha (#46); «الأداء الحالي للنماذج غير كافي» (Itqan `/d/584`).
  PR #43 reports 1:3 being matched to the basmala of 1:1 in the verse search.
- **Papers and press.** The paper was an ICML 2026 workshop poster. Its only citation (Tadabur,
  arXiv 2604.18932) reuses the segmenter idea. **No independent evaluation exists.**
- **Other phonetizer bugs** from an independent audit (Quran-Lab/Muno459, DV-001…008) were fixed
  in quran-transcript 0.6.0, and re-checked as fixed in our copy. DV-010 (ghunnah 3 at an ayah
  end vs 4 mid-ayah) was kept by the author on purpose.
- **Quran-Lab** (Muno459) is the most serious independent work:
  - **`quran-g2p`:** a separate Hafs-via-al-Shatibiyya phonemizer, with 208 rulings reviewed by
    an ijazah holder and two Umm al-Qura professors, and 98.9% exact agreement with
    quran-transcript. Its `docs/NOTABLE-RULINGS.md` is a cross-check list for the teacher.
    **Licence NPL-1.2** (no charging; derived artifacts count): reference only, never copy its
    data.
  - **Its streaming model card** admits it "transcribes the rule, not the deviation". Muno459
    argues that scoring against the mushaf text rewards a model that ignores the audio.
  - Together this is the strongest public warning that **v3_2 leans toward hearing the correct
    text**.
- **Other apps on v3_2:**
  - iTarek/Quran-Muaalem-iOS (FastAPI + Swift, the same shape as ours);
  - Shaikhy and azani_w_qiblati (int8 ONNX, no accuracy figures);
  - HifzGuide (a 116M student model; its card says v3_2's agreement with itself "varies by tens of
    points across window positions", so clip edges matter);
  - Mihrab al-Quran (~27k learners, bf16);
  - ReciteQuran (a Dart port of the rules).
- **Real-user reports (Itqan):**
  - correct ayat flagged;
  - a quiet hamza at the start dropped;
  - the word-final vowel misheard into the next word;
  - س/ص, ك/ق and ن/م confused;
  - voice detection clipping quiet word starts.

  The design advice from those threads: show unsure words grey, not red.
- **`obadx/qdat_bench`:** the 159-clip learner benchmark (one ayah). Its licence is unanswered.
  It could serve as a small public sanity check.
