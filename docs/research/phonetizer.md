# The phonetizer (quran-transcript 0.6.4+muaalem.1)

The phonetizer builds the expected reading the model's output is compared with, so an error here
is an error in every result. It was audited on 2026-10-16 against Hafs via al-Shatibiyya, running
it read-only on the exact Quran text, with `build_moshaf()` defaults. Reproduce with
`.venv/bin/python -m tools.research.findings phonetizer`.

## How it works, briefly

`phonetizer.py` runs 27 regex passes over the Uthmani text (`OPERATION_ORDER`,
`operations.py:1004`). It keeps a character map throughout, and the end of the text counts as a
stop. The passes, in order:

1. **Text preparation:**
   - spell out the disconnected letters;
   - apply the special-case table (`quran-alphabet.json` → `special_patterns`), which holds every
     reading choice: sakt, يلهث, اركب, تأمنا, ضعف, سلاسلا, ءآل and so on;
   - set the vowel of a hamzat al-wasl at the start.
2. **Spelling cleanup:** alif maqsura, hamza forms, dropping the round-sukun letters and the
   mid-text hamzat al-wasl, the long-sukun alifs (أنا، لكنا، الظنونا…), madd 'iwad, the small
   letters, silah.
3. **The stop:** drop the last vowel; taa marbuta becomes ha at the end and ta elsewhere; the alif
   of the Name is added.
4. **Noon, tanween and idgham:** split the tanween, delete the first letter of each idgham pair,
   resolve two sakin letters meeting.
5. **Ghunnah runs:** 3 for ikhfa and iqlab, 4 for a doubled noon or meem, 3 for idgham into ي/و.
6. **Tasheel and imala.**
7. **Madd,** in this order: munfasil → muttasil at a stop → muttasil → 'ayn → ميم آل عمران →
   lazim → 'arid → leen (N harakat written as N−1 letters) → natural.
8. **Qalqalah.**
9. **Shadda** is doubled.

Sifat are per letter group (`sifa.py:310`): fixed letter sets, plus three special finders for the
lam of the Name, the alif after a letter, and the raa (five light patterns plus the per-word
options).

## Confirmed bugs

| # | Rule | Example → output | Hafs via al-Shatibiyya | Where | Notes |
|---|---|---|---|---|---|
| 1 | Doubled raa at a stop after a kasra | «مُّسْتَمِرٌّ» 54:2 → `رر` **mofakham**; also 54:3, 54:19, 54:38, «ٱلْبِرَّ» 2:177 | Tarqeeq (al-Nashr p.603 lists «وبالبر»; no dispute found) | `sifa.py:269` (also 268, 270): the light pattern allows only `ْ` or the end after the raa, not a shadda | 20 places (14 distinct words); 4 are ayah ends in al-Qamar, so default stops. Also present upstream; no upstream issue |
| 2 | Qalqalah on ط in incomplete idgham | «أَحَطتُ» 27:22, «بَسَطتَ» 5:28, «فَرَّطتُ» 39:56, «فَرَّطتُمْ» 12:80 → ط **moqalqal** | Itbaq and isti'la kept, no qalqalah (al-Nashr p.228; quran-g2p ruling R161 citing al-Jazariyya) | `sifa.py:347-351`: "qalqalah letter with no vowel after" | The phoneme string is already right (no ڇ); only the sifa label is wrong |
| 3 | Leen madd on a final sakin waw/yaa at a stop | «أَوْ» → `ءَووو`, «لَوْ», «خَلَوْا۟», «ٱنتَهَوْا۟» | No madd: a leen 'arid needs a letter after it | `operations.py:940,944`: `[^ّ]` matches the sukun mark | 631 words, none at an ayah end, so it only matters on a stop mid-ayah |
| 4 | Idgham option at يس / ن | `noon_and_yaseen=idgham` → `…سِۦۦٓووو…`: a raw U+0653 leaks into the phonemes, and the 6-count madd comes out as 2 | Izhar only (the idgham is al-Tayyiba) | `operations.py:917` | The option is to be removed anyway (`shatibiyya-sources.md` #7) |
| 5 | Settings declared and never read | `ghonna_lam_and_raa`, `saken_before_hamz`, `takbeer`, `recitation_speed` appear nowhere outside `moshaf_attributes.py` | — | — | Choosing them changes nothing. The first three are al-Tayyiba options, to be removed |
| 6 | Heaviness levels | «قِ» → low_mofakham, but «صِّ» → mofakham | Scholars describe the levels differently | `sifa.py:86-91` | The labelling the model was trained on; leave it |

## Checked and correct

- **Raa:** «قِرْطَاسٍ», «فِرْقَةٍ», «مِرْصَادًا», «إِرْصَادًا» heavy. At a stop, «حِجْرٌ», «ذِكْرِ»,
  «سِحْرٌ», «بِكْرٌ», «ٱلشِّعْرَ», «خَيْرٌ», «قَدِيرٌ» are light, and «ٱلْفَجْرِ», «ٱلْقَدْرِ»,
  «ٱلْعَصْرِ», «ٱلْعُسْرَ», «مَرْيَمَ» heavy. Also correct: «فَٱصْبِرْ صَبْرًا», «رَبِّ ٱرْجِعُونِ»,
  starting with «ٱرْتَابُوا», «مِّرْفَقًا», «مَجْر۪ىٰهَا», and «فِرْقٍ» by its setting.
- **The lam of the Name:** all 2,737 occurrences match "heavy unless the last vowel is a kasra".
- **Hamzat al-wasl at the start:** all 2,003 distinct words were checked, and 383 non-article
  words were checked letter by letter, including «ٱمْرُؤٌا», «ٱمْشُوا», «ٱقْضُوٓا», «ٱؤْتُمِنَ»,
  «ٱضْطُرَّ» and «ٱلِٱسْمُ».
- **Silah:** «فِيهِۦ مُهَانًا», «يَرْضَهُ», «أَرْجِهْ», «فَأَلْقِهْ», «وَيَتَّقْهِ»; no silah in «فِيهِ هُدًى».
- **The seven alifs** and «قَوَارِيرَا» ×2, «ثَمُودَا», «سَلَـٰسِلَا» (fixed).
- **Idgham** of each kind: قد تبين، إذ ظلموا، يلهث ذلك، اركب معنا، قل رب، بل رفعه; and the sakt places.
- **The clear noon** in «الدنيا», «بنيان», «صنوان».
- **Iqlab / ikhfa shafawi, idgham shafawi, izhar shafawi.**
- **The disconnected letters**, including الم الله wasl 2/6 and the clear dal in «كهيعص ذكر».
- **Every madd kind;** «ءَآلْـَٔـٰنَ» with madd or tasheel; «ءَا۬عْجَمِىٌّ»; «لْـَٔيْكَةِ»; تأمنا ishmam/rawm;
  ضعف fath/damm in all three places of 30:54.
- **Al-Anfal → al-Tawba** sakt and wasl.
- **No stray character** outside the phonetic alphabet in a whole-Quran sweep, including every
  ayah junction.

## Our two patches (`vendor/quran-transcript/MUAALEM_PATCHES.md`)

| # | Change | Verdict |
|---|---|---|
| 1 | `operations.py:581-586`: a noon carrying the iqlab mark at the very end of the text becomes a clear sakin noon. «مَنۢ» at a stop: `مَم` → `مَن`; 199 stop texts change. Mid-text iqlab unchanged | **Correct.** The cause of the iqlab (the following baa) is gone at a stop |
| 2 | `sifa.py:230-236`: the القطر pattern no longer needs the hamzat al-wasl, and the مصر pattern accepts the shadda of «مِّصْرَ» 12:21. Upstream ignored the tarqeeq setting there | **Correct.** It only makes an existing option work; the defaults match the teacher's preference |

Neither patch makes anything worse. Bugs #1 and #2 above are present upstream too.

The vendored copy differs from the PyPI sdist (sha256 `3d99f3a0…103a`) in exactly these two
patches, the version line, and the added `MUAALEM_PATCHES.md` (`provenance.md`).

## The rules table checked against the output

- **Both-valid word indices** are all right: نذر ×6, فرق, مصر ×4, القطر, and «ٱلِٱسْمُ» = word 29.
- **The fixed settings take effect:** سلاسلا and آتان keep the alif or yaa at a stop. So do the
  defaults: مصر heavy, القطر light. «فرق» at a stop is always heavy.
- **The two "pronunciation" both-valid entries are never read by the analysis.** The meem entry
  is enforced separately (`tajweed.py:35-38`); the «ٱلِٱسْمُ» one is not.
- **Settings left open that al-Shatibiyya doesn't give:** يس/ن idgham, يلهث/اركب izhar, 'ayn 2,
  ghunnah in lam/raa, sakt before hamza, صاد in يبسط/بسطة, سين in بمصيطر. All to be removed
  (`shatibiyya-sources.md`).
- **The 'ayn madd is tagged "Leen Madd"** in the rules, so `madd_lengths` accepts 2 there anyway.
  The fix must cover that too.
