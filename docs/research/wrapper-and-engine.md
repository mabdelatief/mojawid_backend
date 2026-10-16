# The model's wrapper (quran-muaalem 0.2.2), the lab's fixes, and ours

Audited 2026-10-16 by reading `quran_muaalem` (installed, byte-identical to the PyPI wheel), the
error explainer in quran-transcript, the lab's `muaalem_lab/`, and `app/engine/`. The checks ran
on CPU with hand-made "heard" scripts and no model loaded. Reproduce the engine findings with
`.venv/bin/python -m tools.research.findings` (names in brackets below).

## The wrapper's problems

| Issue | Where | Effect | Do we use it? |
|---|---|---|---|
| **Letter pairing for the sifat table merges neighbouring pairs whenever one group's text is inside the next (`لَ` in `للَ`)** | `quran_muaalem/explain.py:39-76` `merge_same_phoneme_group`, called by `segment_groups` | On a **perfect** recitation, 1,030 of 6,236 ayat lose rows (1,200 rows), and 211 ayat show 227 made-up tafkheem mismatches, almost all on the lam of «ٱللَّهُ», which gets compared with the lam before it [`sifat_quran`, `sifat_najm23`] | **Yes**, through `app/engine/pipeline/qm.py` → `analysis/sifat.py`. Not reported upstream |
| A final one-frame letter after a blank is dropped | `decode.py:343-371` | The last letter is lost | No (our `ctc.py`) |
| Sifat probabilities replaced by label ids on the realign path | `decode.py:524-525` (also upstream issue #6, open, unanswered) | Garbage confidences | No |
| Sifat paired with letters by position; realign only when the heard text is shorter, and toward the *expected* sifat | `inference.py:30-42`, `decode.py:502-525` | One merged value shifts every later letter; sifat pulled toward correct | No (our `decode.py` lines up by order) |
| bf16 forward pass by default; softmax on bf16 logits | `inference.py:58,75,144-151` | Probabilities quantised; doubt ratios near the threshold can move | We use bf16 logits with an fp32 softmax. **bf16 vs fp32 never measured** |
| Group alignment on the first character only | `decode.py:180`, `error_explainer.py:42-43` | Groups that differ after the first character count as "equal" | Partly |
| Every changed group carrying a rule becomes a tajweed row, even at the right length | `error_explainer.py:371-411` | False alarms | Handled by our `is_false_alarm` |
| Imala, sakt and mukhtalasa not reported (TODO); the ghunnah rule never attached; `IdghamKamel` commented out | `error_explainer.py:424-426`, `tajweed_rulses.py:215`, `operations.py:649` | Missed mistakes | Handled by `missed.py` and `ghunnah_state` |
| `MaddRule.count` ignores a trailing haraka | `tajweed_rulses.py:89-94` | A stray haraka after a madd is hidden | **Yes**, see "idraj" below |
| No length cap or chunking; the engine caps audio at 15 s, and training clips were ≤ 30 s | `engine/settings.py:177` | Accuracy past 30 s unmeasured | We allow 60 s and warn past 30 s |

## The lab's fixes (tajweed_ai), and how they hold up

| Fix | Verdict | Risk |
|---|---|---|
| Own greedy CTC with the edge fixed; fp32 softmax | Correct | Logits are still bf16 |
| Sifat lined up by order, plus "sure" gating | An improvement | Only affects the `sure` flags |
| Models pinned and offline | Correct | — |
| Patched phonetizer | Correct (`phonetizer.md`) | — |
| Rules table | Correct encoding | The madd pair isn't applied to what was heard; 'arid/leen 2/4/6 have no ruling (the sources agree with them: `shatibiyya-sources.md` #19) |
| Pauses from the segmenter: ≥ 0.35 s is a stop, 0.15–0.35 s a soft pause | An improvement | **0.35 s has no recorded measurement.** A hesitation followed by carrying on is counted as mistakes [`hesitation`] |
| Path inference (stops, going back) | A big improvement (Ar-Ra'd 2: 6 → 3 errors; Yusuf: 6 → 1) | It fits the reference to what was heard. A stop mid-word gives scattered letter errors, not "stopped mid-word" |
| Doubt ratio < 10× → uncertain, never counted | An improvement on coin flips | **Set from a gap in 124 places, with no teacher labels.** Uncertain places cluster where the model is weakest (ikhfa, madd ±1), so it can hide real mistakes there. And `mark_doubt` takes the *minimum* over overlapping blocks, so a sure mistake next to an unsure one becomes uncertain |
| Ghunnah named as a state; a single clear noon on ikhfa = izhar | An improvement | Inconsistent: an ikhfa heard as a clear noon *held* is a "wrong letter"; an izhar heard as ikhfa is a "wrong letter" [`ghunnah_states`] |
| False alarm when the madd length is right | Needed | **Length-only.** It hides other changes in the same group: **idraj at «مَّرْقَدِنَا» 36:52 is not counted** [`idraj`] |
| Rows for imala, sakt, mukhtalasa (`missed.py`) | An improvement | All marked "wrong letter", the most serious kind |
| Valid variants: madd length, meem form | The meem follows the ruling | **The madd check is per place: munfasil 5 with muttasil 4 is shown as allowed** (ruled a mistake); mixed lengths aren't flagged (taswiya) [`madd_pairs`] |
| Raum practice, both-valid places, مالیه alternatives | Follow the rulings | — |
| Plain-Arabic text, no ghunnah numbers | Correct | A sakt after a madd letter isn't described |

## Mojawid's fixes over the lab

| Fix (commit) | Verdict | Notes |
|---|---|---|
| Leen allowed-length check no longer adds 1 (c1d29b4) | **Correct** | 1 letter → 2 harakat, 3 → 4, 5 → 6 [`leen_lengths`] |
| Sifat row tagged `exact` when its stretch was heard exactly (7fb846d) | **Wrong cause; treats the symptom.** I blamed the model's sifat output for the «ٱللَّهُ» row. The cause is the wrapper's pairing (above). The row is now `exact` but still compares the wrong letter's sifa, and a real mistake on that letter is hidden | To be redone at the cause: pair rows from the same group alignment the phoneme diff uses |
| "unexpected" ghunnah (7fb846d) | Right for a sakin noon/meem held (the al-Najm 23 case) | **Too broad:** it also fires on a voweled noon heard doubled and held, and on the idgham after a hesitation [`ghunnah_states`, `hesitation`] |
| Leen text (7fb846d) | Right for 4+ harakat | 3 harakat (2 letters) still shows as a shadda «وّْ» [`leen_lengths`] |

## Other engine findings

- **Skipping a whole word slides the comparison onto the next word.** For 103:2 with
  «ٱلْإِنسَـٰنَ» skipped, the rows include a false "missing لَ" and a false haraka on the correctly
  read «لَفِى» [`word_skip`]. The cause is tie-breaking at repeated characters in
  `app/engine/text/phonetic_diff.py` and in explain_error. The تسميع author's "best-drop" idea is
  a usable tie-breaker: if the heard script equals the expected script minus whole words, report
  "word skipped" (`community-and-ecosystem.md`).
- **A crash path.** `decode.py:184-185` raises a plain `ValueError` when the heard script won't
  split into letter groups: a leading haraka, two harakat in a row, or a doubled qalqalah mark.
  That is a 500 rather than an `AnalysisError`. The lab has the same code.
- **A dropped shadda** comes out as `tashkeel delete`, i.e. "wrong haraka". **A fully dropped
  natural madd** (قَالَا → قَالَ) comes out as a tajweed mistake. Both change the word, and the
  severity is a product question.
- **Breath at a stop** (a trailing «ه») shows as an inserted letter, the most serious mark. Not
  measured on our recordings yet.

## The port against the lab

- All 473 engine tests pass, and the 22 L1 goldens match the lab field by field (minus our new
  fields).
- **The goldens cover only the happy path.** Every case but two has 0 rows. Ghunnah states,
  uncertain rows, false alarms beyond 'arid, missed rows, sifat mismatches and stops mid-ayah are
  covered by unit tests only.
