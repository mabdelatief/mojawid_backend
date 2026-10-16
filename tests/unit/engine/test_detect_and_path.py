"""Which ayah a recitation is, and where the reciter stopped, went back or joined ayat, on
recitations built from the phonetizer itself. Ported from tajweed_ai tests/test_detect.py and
tests/test_path.py."""

from __future__ import annotations

from typing import Any

import pytest

from app.engine.pipeline.detect import Detection, detect
from app.engine.pipeline.path import Inferred, infer
from app.engine.pipeline.pauses import Pauses
from app.engine.text.moshaf import build_moshaf
from app.engine.text.phonetic_diff import blocks
from app.engine.text.qt import chunck_phonemes
from app.engine.text.quran_text import basmala_text
from app.engine.text.reference import ayah_phonemes, build_reference_from_structure, phonetize
from app.engine.text.structure import Structure

M = build_moshaf()

# ---------- detect ----------

# What the model heard (2026-10-14) from a reciter who read Al-Insan 9 up to «لِوَجْهِ ٱللَّهِ»,
# stopped, went back to «إِنَّمَا» and read the whole ayah.
RESTART_76_9 = "ءِننننَمَاانُطعِمُكُملِوَجڇهِللَااااهءِننننَمَاانُطعِمُكُملِوَجهِللَااهِلَاانُرِۦۦدُمِںںںكُمجَزَااااءَوووَلَااشُكُۥۥرَاا"


def ayat(sura: int, a: int, b: int) -> str:
    return "".join(ayah_phonemes(sura, x, M) for x in range(a, b + 1))


def first(det: Detection | None) -> tuple[int, int, int]:
    assert det is not None
    c = det.candidates[0]
    return c.sura, c.aya, c.aya_end


def test_going_back_to_the_ayah_start_is_still_that_ayah() -> None:
    det = detect(RESTART_76_9, M)
    assert first(det) == (76, 9, 9)
    assert det is not None
    assert (det.ranges[0].sura, det.ranges[0].aya, det.ranges[0].aya_end) == (76, 9, 9)
    # the range with the previous ayah stays among the ranges, for scoring with the stops in view
    assert (76, 8, 9) in [(c.sura, c.aya, c.aya_end) for c in det.ranges]


def test_a_clean_ayah() -> None:
    det = detect(ayat(76, 9, 9), M)
    assert first(det) == (76, 9, 9)
    assert det is not None and det.clear


def test_scoring_the_next_ayah_does_not_drop_a_real_start() -> None:
    det = detect(ayat(76, 8, 9), M)
    assert first(det) == (76, 8, 9)
    assert det is not None and det.clear


def test_basmala_before_fatiha_is_ayah_one() -> None:
    det = detect(phonetize(basmala_text(), M).phonemes + ayat(1, 2, 2), M)
    assert det is not None
    assert det.prefixes == ()
    assert first(det)[:2] == (1, 1)


# ---------- path ----------

GROUP_FRAMES = 2  # each heard letter group lasts 2 frames (80 ms)
PAUSE_FRAMES = 20  # a real pause: 0.8 s
SOFT_FRAMES = 6  # a short silence: 0.24 s

Heard = tuple[list[str], list[tuple[int, int]], Pauses]


def recite(parts: list[tuple[str, int]]) -> Heard:
    """What the model would hear for (phonetic text, silence after it in frames) parts: heard
    groups, their frames and the pauses, as the decoder gives them."""
    groups: list[str] = []
    frames: list[tuple[int, int]] = []
    speech: list[tuple[float, float]] = []
    raw: list[tuple[float, float]] = []
    t = 0
    for text, silence in parts:
        start = t
        for x in chunck_phonemes(text):
            groups.append(x)
            frames.append((t, t + GROUP_FRAMES))
            t += GROUP_FRAMES
        raw.append((start * 0.04, t * 0.04))
        t += silence
    for a, b in raw:  # speech stretches: raw ones merged across silences shorter than a pause
        if speech and a - speech[-1][1] < 0.35:
            speech[-1] = (speech[-1][0], b)
        else:
            speech.append((a, b))
    return groups, frames, Pauses(speech, raw, ends_in_speech=False, starts_in_speech=False)


def words_of(sura: int, aya_start: int, aya_end: int | None = None) -> Structure:
    return Structure(sura, aya_start, aya_end or aya_start)


def stretch(sel: Structure, a: int, b: int) -> str:
    """Words a..b of the selection phonetized as one stretch, as the reference writes a segment."""
    words = sel.words()
    return str(phonetize(" ".join(w.text for w in words[a : b + 1]), M, sel.sura).phonemes)


def run(sel: Structure, heard: Heard) -> Inferred:
    inf = infer(sel, M, *heard)
    assert inf is not None
    return inf


def blocks_for(inf: Inferred, groups: list[str]) -> list[dict[str, Any]]:
    ref = build_reference_from_structure(inf.structure, M)
    return blocks(ref.phonetic.phonemes, "".join(groups))


def kinds(inf: Inferred) -> list[str]:
    return [b.kind for b in inf.boundaries if b.kind != "joined"]


def test_stop_inside_an_ayah() -> None:
    sel = words_of(13, 2)  # stopped at ٱلْعَرْشِ (word 10)
    n = len(sel.words())
    heard = recite([(stretch(sel, 0, 10), PAUSE_FRAMES), (stretch(sel, 11, n - 1), 0)])
    inf = run(sel, heard)
    assert inf.structure.segments == [(0, 10), (11, n - 1)]
    assert kinds(inf) == ["stop"]
    assert blocks_for(inf, heard[0]) == []
    assert inf.distance == 0 < inf.default_distance


def test_stop_then_going_back_five_words() -> None:
    sel = words_of(13, 2)
    n = len(sel.words())
    heard = recite([(stretch(sel, 0, 10), PAUSE_FRAMES), (stretch(sel, 5, n - 1), 0)])
    inf = run(sel, heard)
    assert inf.structure.segments == [(0, 10), (5, n - 1)]
    assert [(b.kind, b.resume_word) for b in inf.boundaries if b.kind != "joined"] == [
        ("stop_back", 5)
    ]
    assert blocks_for(inf, heard[0]) == []


def test_going_back_that_was_not_heard_is_not_invented() -> None:
    sel = words_of(13, 2)
    n = len(sel.words())
    inf = run(sel, recite([(stretch(sel, 0, 10), PAUSE_FRAMES), (stretch(sel, 11, n - 1), 0)]))
    assert all(b.kind != "stop_back" for b in inf.boundaries)


def test_joined_ayat() -> None:
    sel = words_of(112, 1, 2)
    n = len(sel.words())
    heard = recite([(stretch(sel, 0, n - 1), 0)])
    inf = run(sel, heard)
    assert inf.structure.segments == [(0, n - 1)]
    assert any(b.kind == "joined" for b in inf.boundaries)
    assert blocks_for(inf, heard[0]) == []


def test_a_stop_on_a_full_haraka_stays_a_mistake() -> None:
    # paused after ٱلْعَرْشِ but said it as if connected: the pause makes it a stop, so the
    # reference has the stop's sukoon and the haraka is flagged
    sel = words_of(13, 2)
    n = len(sel.words())
    connected = stretch(sel, 0, 11)
    as_if_connected = connected[: len(connected) - len(stretch(sel, 11, 11))]
    heard = recite([(as_if_connected, PAUSE_FRAMES), (stretch(sel, 11, n - 1), 0)])
    inf = run(sel, heard)
    assert inf.structure.segments == [(0, 10), (11, n - 1)]
    assert blocks_for(inf, heard[0]), "the haraka at the stop must stay flagged"


def test_a_sukoon_without_a_pause_stays_a_mistake() -> None:
    sel = words_of(13, 2)
    n = len(sel.words())
    heard = recite([(stretch(sel, 0, 10) + stretch(sel, 11, n - 1), 0)])
    inf = run(sel, heard)
    assert inf.structure.segments == [(0, n - 1)]
    assert blocks_for(inf, heard[0]), "a sukoon without stopping must stay flagged"


def test_short_silence_at_an_ayah_end_is_uncertain() -> None:
    sel = words_of(112, 1, 2)
    k = next(i for i, w in enumerate(sel.words()) if w.ayah_last)
    n = len(sel.words())
    inf = run(sel, recite([(stretch(sel, 0, k), SOFT_FRAMES), (stretch(sel, k + 1, n - 1), 0)]))
    assert any(b.kind.startswith("uncertain") for b in inf.boundaries)


def test_another_text_is_not_inferred() -> None:
    other = words_of(1, 2)
    heard = recite([(stretch(other, 0, len(other.words()) - 1), 0)])
    assert infer(words_of(13, 2), M, *heard) is None


def test_opening_then_a_stop() -> None:
    sel = Structure(67, 1, 1, prefixes=("basmala",))
    n = len(sel.words())
    basmala = phonetize(basmala_text(), M).phonemes
    heard = recite(
        [(basmala, PAUSE_FRAMES), (stretch(sel, 0, 2), PAUSE_FRAMES), (stretch(sel, 3, n - 1), 0)]
    )
    inf = run(sel, heard)
    assert inf.structure.prefixes == ("basmala",)
    assert inf.structure.segments == [(0, 2), (3, n - 1)]
    assert blocks_for(inf, heard[0]) == []


def test_only_a_path_unlike_the_default_needs_confirming() -> None:
    sel = words_of(112, 1, 2)
    k = next(i for i, w in enumerate(sel.words()) if w.ayah_last)
    n = len(sel.words())
    plain = run(sel, recite([(stretch(sel, 0, k), PAUSE_FRAMES), (stretch(sel, k + 1, n - 1), 0)]))
    assert not plain.differs  # a stop at each ayah end: the default
    assert run(sel, recite([(stretch(sel, 0, n - 1), 0)])).differs


def _maleeyah() -> tuple[Structure, int, int]:
    sel = words_of(69, 28, 29)  # ... مَالِيَهْ ۜ (28) هَلَكَ عَنِّى سُلْطَـٰنِيَهْ (29)
    k = next(i for i, w in enumerate(sel.words()) if w.ayah_last)
    return sel, k, len(sel.words())


@pytest.mark.parametrize("choice", ["sakt", "idgham"])
def test_maleeyah_connected_with_sakt_or_idgham_is_correct(choice: str) -> None:
    # teachers' ruling (2026-10-14): connected, sakt and idgham are both correct
    sel, k, n = _maleeyah()
    text = " ".join(w.text for w in sel.words())
    connected = phonetize(text, M.model_copy(update={"sakt_maleeyah": choice}), sel.sura).phonemes
    heard = recite([(connected, 0)])
    inf = run(sel, heard)
    assert inf.structure.segments == [(0, n - 1)]
    assert inf.structure.special == {k: choice}
    assert blocks_for(inf, heard[0]) == []


def test_maleeyah_with_a_pause_is_a_stop() -> None:
    sel, k, n = _maleeyah()
    heard = recite([(stretch(sel, 0, k), PAUSE_FRAMES), (stretch(sel, k + 1, n - 1), 0)])
    inf = run(sel, heard)
    assert inf.structure.segments == [(0, k), (k + 1, n - 1)]
    assert inf.structure.special == {}
    assert blocks_for(inf, heard[0]) == []


def test_going_back_to_the_ayah_start_after_most_of_it() -> None:
    sel = words_of(76, 9)
    n = len(sel.words())
    heard = recite([(stretch(sel, 0, 3), PAUSE_FRAMES), (stretch(sel, 0, n - 1), 0)])
    inf = run(sel, heard)
    assert inf.structure.segments == [(0, 3), (0, n - 1)]
    assert [(b.kind, b.resume_word) for b in inf.boundaries] == [("stop_back", 0)]
    assert blocks_for(inf, heard[0]) == []
    assert inf.distance == 0


def test_the_whole_ayah_twice() -> None:
    sel = words_of(1, 2)
    n = len(sel.words())
    inf = run(sel, recite([(stretch(sel, 0, n - 1), PAUSE_FRAMES), (stretch(sel, 0, n - 1), 0)]))
    assert inf.structure.segments == [(0, n - 1), (0, n - 1)]
    assert inf.distance == 0


def test_the_ayah_then_another_text_is_not_inferred() -> None:
    sel = words_of(76, 9)
    other = words_of(2, 255)
    heard = recite(
        [(stretch(sel, 0, len(sel.words()) - 1), PAUSE_FRAMES),
         (stretch(other, 0, 15), PAUSE_FRAMES), (stretch(other, 16, 30), 0)]
    )  # fmt: skip
    assert infer(sel, M, *heard) is None
