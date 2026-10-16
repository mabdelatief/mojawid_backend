# The model's paper: arXiv 2509.00094 (v2)

"Automatic Pronunciation Error Detection and Correction of the Holy Quran's Learners Using Deep
Learning", Abdelfttah, Khalil and Abbas (Ain Shams), 37 pages. Read in full 2026-10-16 (PDF and
HTML), cross-checked against the vendored quran-transcript and the per-recitation attributes in the
HF dataset `obadx/muaalem-annotated-v3`.

## What it claims

- **Quran Phonetic Script (QPS):** 11 output levels.
  - **Phonemes:** 43 symbols: the 28 consonants, alif, waw/yaa madd, three harakat,
    fatha_momala, alif_momala, hamza_mosahala, the qalqalah mark, noon/meem mokhfah, the sakt
    mark, dama_mokhtalasa.
  - **Sifat:** 10 levels. Each is a yes/no choice except shidda (three values) and tafkheem
    (mofakham / moraqaq / low_mofakham). Not modelled: inhiraf, isti'la/istifal, idhlaq.
- **Lengths are written as repeats:**
  - madd is one symbol per haraka;
  - a leen madd of N harakat is N−1 letters;
  - a doubled noon/meem is 3 symbols;
  - ikhfa and iqlab are 3 hidden-noon/meem symbols;
  - idgham with ghunnah into ي/و doubles the ي/و.
- **Ishmam is not encoded,** and neither is rawm or ishmam at a stop. The only rawm written is
  in تأمنا.
- **37 "Moshaf attributes"** describe each recitation's choices. A 26-step regex phonetizer turns
  the Uthmani text plus those attributes into the expected script.
- **Data:**
  - 22 reciters, 27 complete recitations, 848 h, all male professional studio recordings.
  - Segmented at pauses, transcribed by Tarteel Whisper, then fuzzy-matched to the text. About
    5,400 of 286K segments were fixed by hand (text, not tajweed).
- **Training:** wav2vec2-BERT 2.0 with 11 CTC heads, one epoch, bf16, clips ≤ 30 s.
- **Results:**
  - Professional test set: phoneme PER 0.54%.
  - Learner benchmark (`qdat_bench`, 159 clips of a single ayah, 5:109, labelled by one hafiz,
    120 of them women): phoneme PER 5.78%, "tajweed F1" 0.758 = the mean of noon mushaddada
    0.869, ikhfa 0.453 and qalqalah 0.953.
  - Ikhfa detail: a clear noon was caught with recall 0.47 at precision 1.0, and partial ikhfa
    never.

## The issues that matter to us

Category key: **W** = wrong for Hafs via al-Shatibiyya; **S** = simplification; **I** = an error
inside the paper; **M** = method.

| # | Issue | Where | Cat. |
|---|---|---|---|
| 1 | Munfasil 2 and 3 (and 6) offered as "Hafs"; three sections give three value sets | §4.2, A.4, A.6 | W, I |
| 2 | Muttasil 2 or 3, and 6 when connected | A.6.4 vs A.4 | W, I |
| 3 | No munfasil ≤ muttasil rule, no "same length throughout" (taswiya) | A.4 | S |
| 4 | 'Ayn of كهيعص/عسق offered as 2 | A.4 | W |
| 5–10 | General/local sakt before a hamza, idraj at the 4 sakt places, takbeer, ghunnah in lam/raa, idgham at يس/ن, izhar at يلهث/اركب — all offered as Hafs options; all only in al-Tayyiba (`shatibiyya-sources.md`) | A.4 | W |
| 11 | سين/صاد in the four words: the options mix both paths | A.4 | W in part (`shatibiyya-sources.md` #10) |
| 12 | A raa "without tikrar" framed as an error, and every raa labelled mokarar. The teaching (al-Jazariyya «وأخف تكريرا إذا تشدد») is that over-trilling is the error | §7, Table 11 | W/S |
| 13 | Isti'la replaced by contextual tafkheem; inhiraf dropped "as it describes the shidda/rakhawa spectrum" (it doesn't) | §3.1 | S |
| 14 | "low_mofakham" undefined. In the code it applies only to غ خ ق with kasra; ص ض ط ظ with kasra get plain mofakham | Table 11 | S |
| 15 | Madd alif labelled "hams" in the flagship example (alif is majhur; the code is right) | Table 3/17 | I |
| 16 | Idgham with ghunnah into ي/و: "two repetitions" in A.6.5, three in the example and the code. Its ghunnah isn't marked on the ghunnah level | A.6.5, §3 | S, I |
| 17 | Ghunnah measured in "sakin-noon units", not harakat; the different kinds of ghunnah aren't on one scale | A.6.5 | S |
| 19 | Ishmam described as "nasalization" | A.4 | W (wording) |
| 20 | ماليه هلك placed in "Al-Ahqaf" (it is al-Haqqah 69:28–29) | A.4 (also the dataset card) | I |
| 21 | Hamzat al-wasl: "proper nouns" take kasra and "the third root letter" decides. In fact it's the closed noun list and the third letter of the word; the examples come out right | A.6.9 | S |
| 22 | Tasheel described as "toward the following madd letter" (it is toward the hamza's own vowel) | A.6.15 | S |
| 23 | Qalqalah is yes/no only, with no levels | Table 11 | S |
| 24 | "Captures all pronunciation errors for Hafs (except Ishmam)" | Abstract | Overclaim |
| 25 | "Describes what the reciters actually said". The labels are generated from the text plus one attribute set per recitation, not from listening | A.6 | **M** |
| 26 | "No LM, so it captures what the user said". An encoder trained only on correct sequences learns the expected text anyway; the ikhfa result shows half of the clear-noon errors heard as correct | §5 | **M** |
| 27 | The learner evaluation is one ayah, one listener, 159 clips and three rule families | §6.2 | M |
| 28 | The benchmark's "golden" munfasil is "2 or 4" | Table 13 | W |
| 29 | "84.7% on female recitations" is actually the average over all 159 clips, 39 of them male | §6.2 | I |
| 30, 31 | Swapped RMSE values; a recitation "excluded" but still in the tables and the data | Table 9, §4.6 | I |

The full list of 33, with confidence levels, is in the audit notes this file was written from. The
two rows marked "teachers' call" in those notes, the meem with closed lips or a gap and «فرق» at a
stop, were already ruled on in the lab (`teacher-rulings.md` #6 and #8).

## The released attribute data

These counts come from `moshaf_meta.json` in `obadx/muaalem-annotated-v3`:
- munfasil 2 in **13 of the 27** recitations, including test recitations 29 and 30; munfasil 5 in
  none;
- idraj at من راق / بل ران in 8;
- 'ayn 2 in 8;
- بمصيطر with سين in 1.

So about half the training audio follows al-Tayyiba choices. That's fine for what the model
*hears*. Our expected reading must always be built from al-Shatibiyya settings, and the paper's
professional-test numbers are mostly measured on qasr recitations.

There is also a labelling issue, quran-muaalem #45, open and unanswered: the training labels end
**nine ayat with an alif where the stop reads ha** (taa marbuta with tanween fath): 56:7, 69:10,
69:14, 74:52, 79:11, 88:4, 88:11, 89:28 and 98:2. The model was trained on the pre-0.6.0
phonetizer output; our phonetizer gives ha. At those stops the model may hear an alif even when the
reciter says ha.

## What it gets right, and why that still matters

- The letter groups for each sifa are correct. So are the 15 ikhfa letters, iqlab treated like
  ikhfa shafawi, leen ≤ 'arid, and both readings of الم الله.
- The special words are handled: مجريها, ءأعجمي, تأمنا, سلاسلا, آتان, مصر, القطر, نذر, يسر.
- On ikhfa and shadda-ghunnah, a mistake the model *does* flag was right every time (precision
  1.0 on a small set). It misses many, but rarely accuses wrongly. That fits our rule that an
  unsure place is never counted.
- Separate sifat heads, and a phonetizer driven by attributes, let us build a strictly
  al-Shatibiyya reference.
- The model card is an unfilled template: base model, dataset, MIT licence, and "cer" as the
  metric. It neither confirms nor contradicts the paper.
