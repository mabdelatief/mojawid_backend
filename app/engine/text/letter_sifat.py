"""A letter's natural sifat: the values its letter has by definition.

Ported from tajweed_ai `muaalem_lab/labels.py` (_letter_sifat, SIFAT_LEVELS). The decoder lines
each sifat output up against these (pipeline/decode.py).
"""

from app.engine.text.qt import alph, parse_tafkheem_sifa

SIFAT_LEVELS = (
    "hams_or_jahr", "shidda_or_rakhawa", "tafkheem_or_taqeeq", "itbaq", "safeer",
    "qalqla", "tikraar", "tafashie", "istitala", "ghonna",
)  # fmt: skip

_PHG = alph.phonetic_groups


def _shidda(p: str) -> str:
    if p in _PHG.shidda:
        return "shadeed"
    return "between" if p in _PHG.between_shidda_rakhawa else "rikhw"


def natural_sifat(groups: list[str], k: int) -> dict[str, str]:
    """Sifat of group k from its letter, exactly as quran-transcript's process_sifat does, except
    the context rules for ر, the lam of Allah and the alif after it."""
    g = groups[k]
    p = g[0]
    try:
        tafkheem = str(parse_tafkheem_sifa(groups, k))
    except ValueError:
        tafkheem = "moraqaq"  # a noon_mokhfah or alif at the edge of an edited label
    return {
        "phonemes": g,
        "hams_or_jahr": "hams" if p in _PHG.hams else "jahr",
        "shidda_or_rakhawa": _shidda(p),
        "tafkheem_or_taqeeq": tafkheem,
        "itbaq": "motbaq" if p in _PHG.itbaaq else "monfateh",
        "safeer": "safeer" if p in _PHG.safeer else "no_safeer",
        "qalqla": "moqalqal" if g[-1] not in _PHG.harakat and p in _PHG.qalqal else "not_moqalqal",
        "tikraar": "mokarar" if p in _PHG.tikrar else "not_mokarar",
        "tafashie": "motafashie" if p in _PHG.tafashie else "not_motafashie",
        "istitala": "mostateel" if p in _PHG.istitala else "not_mostateel",
        "ghonna": "maghnoon" if p in _PHG.ghonna else "not_maghnoon",
    }
