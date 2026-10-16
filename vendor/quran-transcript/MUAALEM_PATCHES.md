# Muaalem patches to quran-transcript 0.6.4

This is the published source of `quran-transcript` 0.6.4 (PyPI sdist, sha256
`3d99f3a023085dda0a7681af8bcec7b51e96479cd08e0c7e38dad2a6e051103a`, MIT licence), with the
patches below. The version is `0.6.4+muaalem.N`. Bump N with every change here, because the
version is recorded with every recording and label (`collect.versions()`).

Each patch is marked in the code with `# muaalem patch N`. Each has a test in
`tests/test_phonetizer_patches.py` at the repo root. The diff of the whole Quran against the
unpatched phonetizer (every ayah, stopped after every word) changes only the places named here.

| N | File | What was wrong | Rule (Hafs via al-Shatibiyya) |
|---|---|---|---|
| 1 | `phonetics/operations.py` (`PrepareGhonnaIdghamIqlab`) | A stop on a noon marked for iqlab («مِنۢ» 2:87, «مَنۢ» 36:52) gave a meem | Iqlab happens only before the baa that follows. At a stop the noon is clear and sakin |
| 2 | `phonetics/sifa.py` (`SPECIAL_RAA_PATTERNS`) | The `raa_alqitr` option (ٱلْقِطْرِ 34:12) needed the hamzat al-wasl, which is removed mid-text. The `raa_misr` option missed «مِّصْرَ» (12:21) because of the shadda on the meem. So both options were ignored unless the segment started at that word | At a stop both ways are valid for these two words. The reading setting must decide |

Released as `0.6.4+muaalem.1`.

**Whole-Quran check (2026-10-13).** Every ayah was read with a stop after every word (77,433 texts,
Hafs defaults) through the original and the patched phonetizer, and the outputs were compared:
- 199 texts changed by patch 1, all of them a stop on a noon carrying the iqlab mark: «مِنۢ»,
  «عَنۢ», «مَنۢ», «لَئِنۢ», «تَكُنۢ», «أَكُنۢ», «لَٰكِنۢ», «يَأْذَنۢ», …. All now end on a
  clear noon.
- 1 text changed by the rules table, not by a patch: «سَلَـٰسِلَا۟» stopped with the alif, per the
  teachers' ruling.
- Nothing else changed: no other letters and no sifat. Patch 2 only makes a non-default
  option work, so it changes nothing under the defaults.
