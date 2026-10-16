# Muaalem patches to quran-transcript 0.6.4

This is the published source of `quran-transcript` 0.6.4 (PyPI sdist, sha256
`3d99f3a023085dda0a7681af8bcec7b51e96479cd08e0c7e38dad2a6e051103a`, MIT licence), with the
patches below. The version is `0.6.4+muaalem.N`. Bump N with every change here, because the
version is recorded with every recording and label (`collect.versions()`).

Each patch is marked in the code with `# muaalem patch N`. Each has a test: patches 1 and 2 in
tajweed_ai's `tests/test_phonetizer_patches.py`, and all three in mojawid_backend's
`tests/unit/engine/test_phonetizer_patches.py`. The diff of the whole Quran against the
unpatched phonetizer (every ayah, stopped after every word) changes only the places named here.

| N | File | What was wrong | Rule (Hafs via al-Shatibiyya) |
|---|---|---|---|
| 1 | `phonetics/operations.py` (`PrepareGhonnaIdghamIqlab`) | A stop on a noon marked for iqlab («مِنۢ» 2:87, «مَنۢ» 36:52) gave a meem | Iqlab happens only before the baa that follows. At a stop the noon is clear and sakin |
| 2 | `phonetics/sifa.py` (`SPECIAL_RAA_PATTERNS`) | The `raa_alqitr` option (ٱلْقِطْرِ 34:12) needed the hamzat al-wasl, which is removed mid-text. The `raa_misr` option missed «مِّصْرَ» (12:21) because of the shadda on the meem. So both options were ignored unless the segment started at that word | At a stop both ways are valid for these two words. The reading setting must decide |
| 3a | `phonetics/sifa.py` (light raa, case 2) | A doubled raa at a stop after a kasra («مُسْتَمِرّ» 54:2, «ٱلْبِرّ» 2:177) was heavy, because the rule for a sakin raa after a kasra didn't see the shadda | A raa stopped on after a kasra is light, doubled or not |
| 3b | `phonetics/sifa.py` (`_INCOMPLETE_IDGHAM`, `_merged_incompletely`) | A ط merged incompletely into ت («بَسَطتَ» 5:28, «فَرَّطتُمْ» 12:80, «أَحَطتُ» 27:22, «فَرَّطتُ» 39:56), and a ق into ك when the incomplete نخلقكم setting is chosen, was given qalqalah | That letter is merged into the next, so it has no qalqalah. Its itbaq and isti'la stay |
| 3c | `phonetics/operations.py` (the leen regexes) | A final leen letter at a stop («أَوْ», «لَوْ», «خَلَوْا», «عَلَيْ»…) got a leen madd, though no letter follows it | A leen madd needs a letter after the leen letter, which is stopped on; with none, it is a plain sakin letter |

Released as `0.6.4+muaalem.1` (patches 1 and 2) and `0.6.4+muaalem.2` (patch 3, made in
mojawid_backend from the 2026-10-16 audit, `docs/research/README.md` R5–R7). tajweed_ai stays at
`+muaalem.1`.

**Whole-Quran check (2026-10-13).** Every ayah was read with a stop after every word (77,433 texts,
Hafs defaults) through the original and the patched phonetizer, and the outputs were compared:
- 199 texts changed by patch 1, all of them a stop on a noon carrying the iqlab mark: «مِنۢ»,
  «عَنۢ», «مَنۢ», «لَئِنۢ», «تَكُنۢ», «أَكُنۢ», «لَٰكِنۢ», «يَأْذَنۢ», …. All now end on a
  clear noon.
- 1 text changed by the rules table, not by a patch: «سَلَـٰسِلَا۟» stopped with the alif, per the
  teachers' ruling.
- Nothing else changed: no other letters and no sifat. Patch 2 only makes a non-default
  option work, so it changes nothing under the defaults.

**Whole-Quran check for patch 3 (2026-10-16).** The same 77,433 texts through `+muaalem.1` and
`+muaalem.2`:
- 648 texts end on a leen letter that is now plain sakin (patch 3c), the last letter only.
- 20 texts end on a doubled raa after a kasra, now light (patch 3a): 2:44, 2:177 (twice), 2:189
  (twice), 3:92, 3:117, 5:2, 19:90, 20:7, 22:5, 25:6, 39:23, 45:8, 54:2, 54:3, 54:19, 54:38, 58:9,
  80:34.
- The ط of 5:28, 12:80, 27:22 and 39:56 lost its qalqalah (patch 3b) in every text containing it.
  No ق changed, since the default نخلقكم setting is complete idgham.
- Nothing else changed.
