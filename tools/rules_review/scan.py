"""Where the phonetizer applies each tajweed rule: one pass over the Quran at the default reading
settings, sorting letters into rule kinds by the Uthmani text around them and by what the
phonetizer made of them. The page shows a few of each, spread over the Quran, with the count.
"""

from __future__ import annotations

import collections
import dataclasses
from collections.abc import Callable, Iterable

from app.engine.text.qt import (
    AaredMaddRule,
    LazemMaddRule,
    LeenMaddRule,
    MonfaselMaddRule,
    MottaselMaddPauseRule,
    MottaselMaddRule,
    Qalqalah,
    alph,
)
from tools.rules_review.quran import Ayah, Cluster, all_ayat

U, P = alph.uthmani, alph.phonetics
HARAKAT = U.fatha + U.dama + U.kasra
TANWEEN = U.tanween_fath + U.tanween_dam + U.tanween_kasr
THROAT = U.hamza + U.hamza_above_alif + U.hamza_below_alif + U.haa + U.ayn + U.haa_mohmala
THROAT += U.ghyn + U.khaa
YANMU = U.yaa + U.waw + U.meem + U.noon
MADD_LETTERS = U.alif + U.alif_maksora + U.waw + U.yaa
TWO_LETTER_IDGHAM = {
    "mutajanisain": {(U.taa_mabsoota, U.daal), (U.daal, U.taa_mabsoota),
                     (U.taa_mabsoota, U.taa_mofakhama), (U.thaal, U.zaa_mofakhama),
                     (U.thaa, U.thaal), (U.baa, U.meem)},
    "mutaqaribain": {(U.lam, U.raa), (U.qaf, U.kaf)},
}  # fmt: skip
MADD_KINDS: tuple[tuple[type, str], ...] = (
    (LazemMaddRule, "madd_lazem"),
    (MottaselMaddPauseRule, "madd_mottasel_waqf"),
    (MottaselMaddRule, "madd_mottasel"),
    (MonfaselMaddRule, "madd_monfasel"),
    (AaredMaddRule, "madd_aared"),
    (LeenMaddRule, "madd_leen"),
)
NOON_BY_NEXT = {
    U.baa: "iqlab", U.lam: "idgham_no_ghunnah", U.raa: "idgham_no_ghunnah",
    **dict.fromkeys(THROAT, "izhar_halqi"),
}  # fmt: skip
NORMAL_MADD = "Normal Madd"
SILAH = U.small_waw + U.small_yaa_sila
SPREAD = 5  # examples per kind


@dataclasses.dataclass(frozen=True)
class Hit:
    """One place a rule applies: the ayah and the marked characters."""

    sura: int
    aya: int
    word: int
    start: int
    end: int


def _sakin(c: Cluster) -> bool:
    """No haraka, no shadda, no tanween."""
    return not any(m in HARAKAT + TANWEEN + U.shadda for m in c.marks)


def _noon_kind(ay: Ayah, c: Cluster, n: Cluster) -> str | None:
    ph = ay.phonemes[c.slice[0] : c.slice[1]] if c.slice else ""
    if n.base == U.hamzat_wasl:
        return None
    if P.noon_mokhfah in ph:
        return "ikhfa"
    if n.base in YANMU:
        return "izhar_mutlaq" if n.word == c.word else "idgham_ghunnah"
    return NOON_BY_NEXT.get(n.base)


def _meem_kind(c: Cluster, n: Cluster) -> str | None:
    if n.base == U.hamzat_wasl:
        return None
    if n.base == U.baa:
        return "ikhfa_shafawi"
    if n.base == U.meem:
        return "idgham_mithlayn_meem"
    return "izhar_shafawi"


def _word_plain(ay: Ayah, c: Cluster) -> str:
    return "".join(ch for ch in ay.words[c.word] if ch.isalpha() and ch != U.hamzat_wasl)


def _allah(ay: Ayah, i: int, c: Cluster) -> str | None:
    """The lam of the Name of Allah (the lam with the shadda)."""
    if c.base != U.lam or U.shadda not in c.marks:
        return None
    plain = _word_plain(ay, c)
    if not (plain.endswith("لله") or plain.endswith("للهم")):
        return None
    sifa = ay.sifa_at(c)
    if sifa is None:
        return None
    return "lam_allah_tafkheem" if sifa.tafkheem_or_taqeeq == "mofakham" else "lam_allah_tarqeeq"


def _lam_al(ay: Ayah, i: int, c: Cluster) -> str | None:
    if c.base != U.lam or i == 0 or ay.clusters[i - 1].base != U.hamzat_wasl or not _sakin(c):
        return None
    if ay.clusters[i - 1].word != c.word:
        return None
    n = ay.next_letter(i)
    if n is None or n.word != c.word:
        return None
    plain = _word_plain(ay, c)
    if plain.endswith("لله") or plain.endswith("للهم"):
        return None
    return "lam_shamsiyya" if c.slice is None else "lam_qamariyya"


def _two_letter_idgham(ay: Ayah, i: int, c: Cluster) -> str | None:
    n = ay.next_letter(i)
    if n is None or c.base in MADD_LETTERS + U.noon + U.meem + U.hamzat_wasl or not _sakin(c):
        return None
    if c.base == U.taa_mofakhama and n.base == U.taa_mabsoota:
        return "idgham_naqis_taa"
    if c.slice is not None or U.shadda not in n.marks:
        return None
    if c.base == U.lam and i > 0 and ay.clusters[i - 1].base == U.hamzat_wasl:
        return None
    return _pair_kind(c.base, n.base)


def _pair_kind(a: str, b: str) -> str | None:
    if a == b:
        return "idgham_mithlayn"
    for kind, pairs in TWO_LETTER_IDGHAM.items():
        if (a, b) in pairs:
            return f"idgham_{kind}"
    return None


def _noon_meem(ay: Ayah, i: int, c: Cluster) -> str | None:
    if c.base in (U.noon, U.meem) and U.shadda in c.marks:
        return "ghunnah_mushaddad"
    n = ay.next_letter(i)
    if n is None:
        return None
    if c.base == U.noon and _sakin(c) or any(m in TANWEEN for m in c.marks):
        return _noon_kind(ay, c, n)
    if c.base == U.meem and _sakin(c):
        return _meem_kind(c, n)
    return None


def _letter(ay: Ayah, i: int, c: Cluster) -> str | None:
    if c.base == U.raa and c.slice is not None:
        sifa = ay.sifa_at(c)
        if sifa is not None:
            return "raa_tafkheem" if sifa.tafkheem_or_taqeeq == "mofakham" else "raa_tarqeeq"
    if any(isinstance(r, Qalqalah) for r in c.rules):
        return "qalqalah_waqf" if i == len(ay.clusters) - 1 else "qalqalah_wasl"
    return None


def _madd(ay: Ayah, i: int, c: Cluster) -> str | None:
    for kind, key in MADD_KINDS:
        if any(isinstance(r, kind) for r in c.rules):
            if key in ("madd_lazem", "madd_leen") and _in_openings(ay, c):
                return "madd_lazem_harfi" if key == "madd_lazem" else "madd_alayn"
            return "madd_lazem_kalimi" if key == "madd_lazem" else key
    if any(r.name.en == NORMAL_MADD for r in c.rules) and c.base not in SILAH:
        return "madd_normal"
    return None


def _silah_iwad(ay: Ayah, i: int, c: Cluster) -> str | None:
    """Madd al-sila (the small waw / yaa after haa al-kinaya) and madd al-'iwad (a stop on
    tanween fath)."""
    if c.base in SILAH and c.rules and i > 0 and ay.clusters[i - 1].base == U.haa:
        monfasel = any(isinstance(r, MonfaselMaddRule) for r in c.rules)
        return "madd_silah_kubra" if monfasel else "madd_silah_sughra"
    last = len(ay.clusters) - 1
    tail = i == last or (i == last - 1 and ay.clusters[last].base in (U.alif, U.alif_maksora))
    if tail and U.tanween_fath in c.marks and c.base != U.taa_marboota:
        return "madd_iwad"
    return None


def _in_openings(ay: Ayah, c: Cluster) -> bool:
    """A word of the opening letters (الٓمٓ، حمٓ، …)."""
    word = ay.words[c.word]
    return any(word in k.split(" ") for k in U.hrof_moqtaa_disassemble)


def _phonetic_marks(ay: Ayah, i: int, c: Cluster) -> str | None:
    ph = ay.phonemes[c.slice[0] : c.slice[1]] if c.slice else ""
    if P.alif_momala in ph or P.fatha_momala in ph:
        return "imala"
    if P.hamza_mosahala in ph:
        return "tasheel"
    if P.dama_mokhtalasa in ph:
        return "ikhtilas"
    if P.sakt in ph:
        return "sakt"
    return None


DETECTORS: tuple[Callable[[Ayah, int, Cluster], str | None], ...] = (
    _madd, _silah_iwad, _allah, _lam_al, _noon_meem, _two_letter_idgham, _letter, _phonetic_marks,
)  # fmt: skip


def _hits(ay: Ayah) -> Iterable[tuple[str, Hit]]:
    for i, c in enumerate(ay.clusters):
        for detect in DETECTORS:
            kind = detect(ay, i, c)
            if kind is not None:
                yield kind, _mark(ay, i, c, kind)


def _mark(ay: Ayah, i: int, c: Cluster, kind: str) -> Hit:
    """The letter, plus the next letter where the rule is between two (idgham, ikhfa, iqlab)."""
    pair = kind.startswith(("idgham", "ikhfa", "iqlab", "izhar")) or kind == "madd_iwad"
    n = ay.next_letter(i) if pair else None
    return Hit(ay.sura, ay.aya, c.word, c.start, n.end if n else c.end)


def scan() -> dict[str, list[Hit]]:
    """kind -> every place, in Quran order."""
    found: dict[str, list[Hit]] = collections.defaultdict(list)
    for ay in all_ayat():
        for kind, hit in _hits(ay):
            found[kind].append(hit)
    return dict(found)


def spread(hits: list[Hit], n: int = SPREAD) -> list[Hit]:
    """n places spread evenly over the Quran: one per surah where there are enough surahs, and
    never two in the same word."""
    by_sura: dict[int, Hit] = {}
    by_word: dict[tuple[int, int, int], Hit] = {}
    for h in hits:
        by_sura.setdefault(h.sura, h)
        by_word.setdefault((h.sura, h.aya, h.word), h)
    pool = list(by_sura.values()) if len(by_sura) >= n else list(by_word.values())
    if len(pool) <= n:
        return pool
    step = (len(pool) - 1) / (n - 1)
    return [pool[round(k * step)] for k in range(n)]
