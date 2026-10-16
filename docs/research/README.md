# Model and tajweed audit (2026-10-16): the review

How sound is what Mojawid tells a reciter? This audit checks:
- the model and its paper;
- the wrapper library;
- the phonetizer;
- every change the lab and Mojawid made;
- what others have found with the same model.

Seven research agents and my own checks on real ayat went into it. Every engine finding has a
reproducer in `tools/research/findings.py` (`.venv/bin/python -m tools.research.findings`).

**The yardstick.** Mojawid is a public app marketed as **Hafs 'an 'Asim via al-Shatibiyya**. It
accepts exactly what that path allows:
- **First, the lab teacher's recorded rulings** (`teacher-rulings.md`, 13 questions, 2026-10-13
  and 10-14).
- **Then the al-Shatibiyya sources** for everything those don't cover (`shatibiyya-sources.md`:
  the poem, al-Wafi, al-Nashr, Hidayat al-Qari).
- **A way only al-Tayyiba gives is removed,** even if it sounds harmless.

**The short answer:**
- **The model is usable.** It is not proven good enough yet.
- **Most concrete defects are in code.** That means the phonetizer, the wrapper and our engine,
  and all of them can be fixed without training.
- **The model's own weakness leans toward missing mistakes, not inventing them.**
- **Several code defects do invent mistakes,** or hide ones the teacher ruled on. Those come
  first.

## Status after fix round 1 (2026-10-16)

Fixed in mojawid_backend, each checked with its reproducer and new tests. Nothing was filed
upstream (the user's decision).

| Item | Status |
|---|---|
| R1, R2 madd pairs and taswiya | Fixed, eb6704c |
| R3 idraj | Fixed, b16c6d5: counted at all four places. 36:52 reads «ا (مد حركتان، سكتة)» → «ا (مد حركتان)»; at 75:27 and 83:14 the missing «نْ (سكتة)» / «لْ (سكتة)» names it |
| R4, R9 both ways accepted | Fixed, 26cebd3 (ضعف in al-Rum only; Hafs reads 8:66 with fath alone) |
| R5, R6, R7 phonetizer | Fixed, 8d7e054: patch 3, `0.6.4+muaalem.2`; whole-Quran diff changed only those places |
| R8 settings | Fixed, f7a8b2a; marked «من متن الشاطبية، للتأكيد» on the review page for the teachers |
| R10 taa-marbuta stops | Open: teacher question 5 |
| C1 sifat pairing | Fixed, 3a60599 |
| C2 skipped word slides | Open: needs its own design |
| C3, C4, C7, C8 | Fixed, b16c6d5 |
| C5 hesitations | Open: teacher question 4, then a pause measurement |
| C6 crash | Fixed, 9063e64 |

## 1. Results that contradict a ruling or al-Shatibiyya

| # | What happens today | Should be | Cause, where | Evidence |
|---|---|---|---|---|
| R1 | Munfasil 5 heard with muttasil 4 is shown as an allowed reading | A mistake (ruling #5) | `analysis/rows.py` `_madd_variant` judges each madd alone; `madd_pairs` is only used for settings | `findings madd_pairs` |
| R2 | Mixed lengths in one recitation (munfasil 4 here, 5 there; 'arid 2 here, 6 there) aren't flagged | A mistake: taswiya (`shatibiyya-sources.md` #19–20) | Not checked anywhere | Code |
| R3 | Idraj at «مَّرْقَدِنَا» (36:52) isn't counted; at 75:27 and 83:14 it is counted, but as a missing letter plus a haraka mistake | A mistake, named as "no sakt" (ruling #4) | `rows.is_false_alarm` compares madd length only; the sakt mark is in the same group | `findings idraj` |
| R4 | Starting with «لِسْمُ» while the setting is «أَلِسْمُ» (or the reverse) is flagged | Both correct (ruling #3) | The "pronunciation" both-valid entry is never read by the analysis | `phonetizer.md` |
| R5 | «مُسْتَمِرٌّ», «مُسْتَقِرٌّ» (al-Qamar 2, 3, 19, 38), «ٱلْبِرَّ» at a stop: the raa is expected heavy | Light | Phonetizer `sifa.py:269` | `findings phonetizer` |
| R6 | «أَحَطتُ», «بَسَطتَ», «فَرَّطتُ»: the ط is labelled with qalqalah | No qalqalah | Phonetizer `sifa.py:347` (sifa label only) | `findings phonetizer` |
| R7 | A stop on a final «وْ/يْ» («أَوْ», «لَوْ») expects a leen madd | Plain sakin | Phonetizer `operations.py:940` | `findings phonetizer` |
| R8 | Settings offer ways only al-Tayyiba gives (§6), and 'ayn 2 is accepted even without the setting, because the 'ayn is tagged "Leen Madd" | Not offered, not accepted | `rules.py` `allowed` doesn't list them; `madd_lengths` | `phonetizer.md` |
| R9 | ضعف (fath/damm), تأمنا (ishmam/rawm), ءآلذكرين/ءآلآن/ءآلله (madd/tasheel), يسر/أسر at a stop: the other valid way is flagged unless chosen beforehand | Both accepted whatever the setting | Not in `both_valid` / `connected_alternatives` | `shatibiyya-sources.md` #11–15 |
| R10 | The nine taa-marbuta ayah ends (56:7, 69:10, 69:14, 74:52, 79:11, 88:4, 88:11, 89:28, 98:2) | A correct «ـه» must not be called a mistake | The model was trained with an alif there (quran-muaalem #45), so it may hear an alif when the reciter says ha | `paper.md` |

## 2. Code defects that invent or hide mistakes

| # | Defect | Effect | Where |
|---|---|---|---|
| C1 | The wrapper's sifat pairing (`merge_same_phoneme_group`) | **On a perfect recitation,** 1,030 ayat lose 1,200 rows of the sifat table, and 211 ayat show 227 made-up tafkheem mistakes, mostly on the lam of «ٱللَّهُ». **My fix 7fb846d blamed the model and only relabelled the row**: the wrong letter's sifa is still compared, and a real mistake there is hidden | `quran_muaalem/explain.py:39-76` via `analysis/sifat.py`; `findings sifat_quran` |
| C2 | Skipping a whole word slides the comparison onto the next word | False "missing letter" and haraka rows on a word read correctly («لَفِى», 103:2) | `text/phonetic_diff.py` and explain_error tie-breaking; `findings word_skip` |
| C3 | «غنة في غير موضعها» (mine, 7fb846d) is too broad | Also fires on a voweled noon read doubled and held, and on the idgham after a hesitation | `rows.unexpected_ghunnah`; `findings ghunnah_states` |
| C4 | Ikhfa/izhar confusions named inconsistently | An ikhfa heard as a clear noon held, or an izhar heard as ikhfa, is a "wrong letter"; one heard as a short clear noon is a tajweed izhar | `rows.ghunnah_state`, `GHUNNAH_HEARD_AS` |
| C5 | A hesitation (a pause ≥ 0.35 s, then carrying on connected) | Counted as mistakes: a haraka at the "stop", sometimes «غنة في غير موضعها» | The pause threshold; `findings hesitation` |
| C6 | Some heard scripts crash the analysis | A 500 instead of an error code | `pipeline/decode.py:184` |
| C7 | A leen madd of 3 harakat is written «وّْ» | Confusing text | `text/readable.py` |
| C8 | `mark_doubt` takes the minimum over overlapping blocks | A sure mistake next to an unsure one becomes uncertain (hidden) | `pipeline/doubt.py` / `analysis/marks.py` |

## 3. The model's own limits (only training changes them)

- **It leans toward hearing the correct reading.** Its labels were generated from the text for
  professional reciters, not made by listening.
  - In the paper's learner test, half the clear-noon-for-ikhfa mistakes were heard as correct.
  - In the تسميع tests, letter changes were caught 3 of 9 times.
  - Quran-Lab's model card describes the same effect ("transcribes the rule, not the deviation").
- **Madd length in the training labels is the reciter's configured length (97.4%).** So
  madd-length mistakes judged from the model's run length are weak evidence.
- **No women, children or beginners in training.** The paper's learner test did include 120 clips
  of women, on one ayah.
- **Edges and short clips:**
  - the output varies with where the clip starts;
  - a single short word does poorly;
  - it over-fits surah openings and al-Fatiha;
  - breath and noise show up as inserted letters.
- **The model's author says it himself** (Itqan forum): «الأداء الحالي للنماذج غير كافي» ("the
  current models' performance is not sufficient").
- **bf16 vs fp32** has never been measured. Our GPU path runs bf16.

## 4. Thresholds set without teacher-checked data

- **"Under 10× → uncertain, never counted"** was set from a gap in 124 places from 28
  recordings. Uncertain places cluster where the model is weakest, so this may hide real
  mistakes in exactly those categories.
- **A pause of 0.35 s counts as a stop.** There is no recorded measurement behind that number.

Both need re-measuring on teacher-labelled recordings (§5).

## 5. Is the model good enough for a public app?

The evidence doesn't say yes or no, because nothing has been measured on the people who will use
it. The plan:
1. **Fix §1 and §2 first.** They are the false and hidden mistakes we actually found.
2. **Build a test set of real users:** about 50–100 recordings of women, men, children,
   beginners and good readers, on ordinary phones, some with real mistakes, each marked by a
   teacher. The lab has the recording and review tooling, and about 28 recordings with partial
   review already.
3. **Measure two numbers:**
   - **false mistakes:** correct places counted as mistakes. This must be very low to launch;
   - **misses,** per kind: letter, haraka, madd, ghunnah, ikhfa.

   Re-measure the 10× and 0.35 s thresholds and bf16 on the same set.
4. **Decide.**
   - **If false mistakes are rare:** launch without fine-tuning. Keep the disclaimer «الملاحظات
     الآلية قد تخطئ ولا تغني عن المعلّم المجاز», and say plainly which kinds of mistake can be
     missed.
   - **If they're frequent for some voices, or dropped and changed letters are missed too
     often:** fine-tune first. That needs listening-based teacher labels, never text-generated
     ones, plus a held-out teacher test set, and proof that the new weights beat the pinned ones.
     It's a project of weeks, mostly spent collecting and labelling.

## 6. The settings decision (Shatibiyya only)

| Remove (al-Tayyiba only) | Keep (al-Shatibiyya) |
|---|---|
| Munfasil 2/3 (already) · idraj at the 4 sakt places (already) · sakt before a hamza · ghunnah in lam/raa · idgham at يس/ن · izhar at يلهث/اركب · 'ayn 2 · صاد in يبسط/بسطة · سين in بمصيطر · takbeer | 'Ayn 4/6 (6 default) · ميم الم الله 2/6 · المصيطرون سين/صاد · ضعف fath/damm · تأمنا ishmam/rawm · ءآل madd/tasheel · يسر/أسر both at a stop · everything in `teacher-rulings.md` |

`recitation_speed` is no tajweed setting, and the phonetizer ignores it; remove it or leave it, but
it changes nothing. A takbeer said between surahs is outside the text: the app neither offers it
nor marks it.

## 7. What holds up

- **Our two phonetizer patches are correct.** The vendored copy differed from upstream in exactly
  those two places (`provenance.md`). Patch 3 (R5–R7) was added after this audit.
- **The lab's decoder replaced the wrapper's buggy one,** with the edge fix, alignment by order,
  and no garbage confidences. Upstream still has the confidence bug (#6).
- **Also correct:** path inference (stops, going back), ghunnah named as a state, false-alarm
  handling for the right madd length, raum as a practice, the both-valid raa places, and the leen
  length fix (c1d29b4).
- **The phonetizer is right almost everywhere it was tested:**
  - the lam of the Name in all 2,737 places;
  - hamzat al-wasl in 2,003 words;
  - silah, the seven alifs, the sakt places and the special words.
- **No upstream update is pending.** The model, segmenter and packages are all still at our pins.

## 8. Fix order (each in its own plan)

1. **Engine (no model):**
   - C1: pair sifat rows from the phoneme alignment; a perfect recitation must give 0 lost rows
     and 0 mismatches over the whole Quran;
   - R1 + R2: madd pairs and taswiya on what was heard;
   - R3: count idraj, and name it;
   - R4, R9: the both-valid places;
   - C2: a word-skip tie-breaker;
   - C3, C4: ghunnah and izhar naming;
   - C6: the crash;
   - C7: leen text;
   - C8: doubt minimum.
2. **Settings and rules (§6, R8).**
3. **Phonetizer patch 3:** R5, R6, R7. Then the whole-Quran diff. (Done; not filed upstream.)
4. **Golden tests** for every case above, plus the nine taa-marbuta stops (R10), surah openings,
   short words and near letter pairs.
5. **The real-user test set and the launch decision** (§5).
6. **Housekeeping:**
   - keep our own copy of the v3_2 weights and their MIT terms (upstream plans a "controlled
     licence" and gating);
   - add a credits text (Tanzil and quran-align are required).

## 9. Still for the teacher (much less than before)

1. **Strict tahrir or mainstream?** Strict would narrow 'ayn, الم الله, المصيطرون, ضعف, تأمنا,
   ءآل and نخلقكم to one way each.
2. **نخلقكم:** keep the incomplete idgham (Makki), or complete only (al-Dani, the poem's source)?
3. **How serious is each kind of mistake?** A dropped shadda (now "wrong haraka"); a fully dropped
   natural madd such as قالا → قال (now "tajweed"); idraj; a missed imala, sakt or ikhtilas (now
   "wrong letter"); a meem or noon sakin held with ghunnah at a stop (now tajweed, «غنة في غير
   موضعها»).
4. **A hesitation** (a pause, then carrying on connected): how should it be judged and worded?
5. **The nine taa-marbuta stops:** when the model hears an alif there, treat it as unsure?

## Files

- **`teacher-rulings.md`:** the recorded rulings, quoted, and whether the engine applies each.
- **`shatibiyya-sources.md`:** the 20 open points with verse quotes and links.
- **`paper.md`:** the paper's claims and its 30+ issues; the training-data facts.
- **`phonetizer.md`:** the phonetizer's bugs, what was found correct, our patches.
- **`wrapper-and-engine.md`:** the wrapper's issues, the lab's and our fixes with verdicts.
- **`community-and-ecosystem.md`:** the تسميع findings, al-Muqri, Itqan, upstream state, other
  apps.
- **`provenance.md`:** what we took from upstream, what we changed, and the licences.
- **`tools/research/findings.py`:** the reproducers.
