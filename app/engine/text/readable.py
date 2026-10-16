"""The model's phonetic script written for people: plain Arabic letters with their marks, plus the
things the script spells out by repeating letters (madd length, ghunnah, qalqalah, sakt) as short
notes. Nobody ever sees the model's own symbols (ۦ ۥ ں ۾ ڇ ۜ …).

Ported from tajweed_ai `muaalem_lab/readable.py`.

Fixed in Mojawid (user's decision, 2026-10-16): a leen madd. The script writes one of N harakat as
its yaa or waw N-1 times with no haraka after, and the lab read 3+ of them as a ghunnah
(«قُرَيّْشْ (غنة)»). A ghunnah held into a yaa or waw always has a haraka after it. A run of 2 (a
leen of 3) is a leen after a fatha, or when the caller knows the group is a leen madd; otherwise it
is a doubled letter at a stop («عَدُوّْ»). A madd that ends in a sakt says so (audit 2026-10-16).
"""

from typing import TypedDict

from app.engine.text.qt import alph, chunck_phonemes

P = alph.phonetics
SUKOON, SHADDA = "ْ", "ّ"
HARAKA: dict[str, str] = {P.fatha: P.fatha, P.dama: P.dama, P.kasra: P.kasra}
MADD_LETTER: dict[str, str] = {P.alif: "ا", P.waw_madd: "و", P.yaa_madd: "ي", P.alif_momala: "ا"}
HIDDEN: dict[str, str] = {P.noon_mokhfah: "ن", P.meem_mokhfah: "م"}
# a leen madd of 4+ harakat: its yaa or waw 3+ times with no haraka after
LEEN_CONSONANTS: str = P.yaa + P.waw
LEEN_RUN = 3
# a consonant written 3+ times is a held ghunnah (mushaddad noon/meem, idgham into ي/و)
GHUNNAH_CONSONANTS: str = P.noon + P.meem + P.yaa + P.waw
# every symbol of the script that is not a plain Arabic letter or haraka
MODEL_SYMBOLS: str = (
    P.yaa_madd + P.waw_madd + P.noon_mokhfah + P.meem_mokhfah + P.qlqla + P.sakt
    + P.dama_mokhtalasa + P.fatha_momala + P.alif_momala + P.hamza_mosahala
)  # fmt: skip
# how a letter was voiced, said of the letter (masculine: «الحرف … ساكنًا»)
VOICED: dict[str, str] = {
    P.fatha: "مفتوحًا", P.dama: "مضمومًا", P.kasra: "مكسورًا", "": "ساكنًا",
    P.qlqla: "ساكنًا مع قلقلة", P.sakt: "ساكنًا مع سكتة", P.dama_mokhtalasa: "مضمومًا باختلاس",
    P.fatha_momala: "مفتوحًا بإمالة",
}  # fmt: skip


class Readable(TypedDict):
    """Letters with marks, and what the marks can't show."""

    text: str
    notes: list[str]


def ar_num(n: int) -> str:
    """Arabic-Indic digits."""
    return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def harakat(n: int) -> str:
    """A madd length in words: حركة واحدة، حركتان، ٤ حركات."""
    if n == 1:
        return "حركة واحدة"
    if n == 2:
        return "حركتان"
    return f"{ar_num(n)} حركات" if 3 <= n <= 10 else f"{ar_num(n)} حركة"


def split_group(group: str) -> tuple[str, int, str]:
    """A letter group as (core letter, run length, residual haraka or mark)."""
    residual = group[-1] if group[-1] in alph.phonetic_groups.residuals else ""
    run = group[:-1] if residual else group
    return run[0], len(run), residual


def _marks(core: str, n: int, residual: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    marks = SHADDA if n >= 2 else ""
    if n >= 3 and core in GHUNNAH_CONSONANTS:
        notes.append("غنة")
    if residual in HARAKA:
        return marks + HARAKA[residual], notes
    marks += SUKOON
    notes += {P.qlqla: ["قلقلة"], P.sakt: ["سكتة"]}.get(residual, [])
    if residual == P.dama_mokhtalasa:
        return marks[:-1] + P.dama, [*notes, "اختلاس"]
    if residual == P.fatha_momala:
        return marks[:-1] + P.fatha, [*notes, "إمالة"]
    return marks, notes


def _group(group: str, leen: bool = False) -> tuple[str, list[str]]:
    core, n, residual = split_group(group)
    if core in LEEN_CONSONANTS and residual not in HARAKA and (n >= LEEN_RUN or (leen and n >= 2)):
        return core + SUKOON, [f"مد {harakat(n + 1)}"]
    if core in MADD_LETTER:
        notes = [f"مد {harakat(n)}"] + (["إمالة"] if core == P.alif_momala else [])
        return MADD_LETTER[core], notes + (["سكتة"] if residual == P.sakt else [])
    if core in HIDDEN:
        return HIDDEN[core], ["إخفاء بغنة"]
    letter, notes = ("أ", ["تسهيل"]) if core == P.hamza_mosahala else (core, [])
    marks, more = _marks(core, n, residual)
    return letter + marks, notes + more


def readable(qps: str, leen: bool = False) -> Readable:
    """{"text": letters with marks, "notes": what the marks can't show}. `leen`: the caller knows
    a sakin yaa/waw run here is a leen madd (an error row carrying the leen rule)."""
    text, notes, after_fatha = "", [], False
    for g in chunck_phonemes(qps) if qps else []:
        t, ns = _group(g, leen or after_fatha)
        after_fatha = g[-1] == P.fatha
        text += t
        notes += [x for x in ns if x not in notes]
    return {"text": text, "notes": notes}


def describe(qps: str, leen: bool = False) -> str:
    """One line, e.g. «ي (مد ٤ حركات)»."""
    r = readable(qps, leen)
    return r["text"] + (f" ({'، '.join(r['notes'])})" if r["notes"] else "")
