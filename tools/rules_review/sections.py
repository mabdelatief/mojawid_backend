"""The review's sections, each item tied to one entry of the rules table, one behaviour of the
analysis or one kind the scan finds. Item ids are stable, so regenerating keeps the answers."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any, get_args

from app.engine.text import rules as R
from app.engine.text.boundaries import special_boundaries
from app.engine.text.moshaf import ReadingOption, moshaf_all_options
from app.engine.text.qt import MoshafAttributes, alph, get_arabic_attributes, get_arabic_name
from app.engine.text.quran_text import ayah_words, surah_list
from app.engine.text.readable import ar_num, harakat
from tools.rules_review import wording as W
from tools.rules_review.quran import (
    ayah_example,
    example,
    load_ayah,
    opening_example,
    ref_ar,
    word_example,
)
from tools.rules_review.scan import Hit, spread

Item = dict[str, Any]
Found = dict[str, list[Hit]]

# where a raa setting applies: its both-valid places
RAA_PLACES: dict[str, Callable[[R.BothValid], bool]] = {
    "raa_nudhur": lambda b: b.sura == 54,
    "raa_firq": lambda b: b.sura == 26,
    "raa_alqitr": lambda b: b.sura == 34,
    "raa_misr": lambda b: b.sura in (10, 12, 43),
}
# settings shown with the scan's examples of the rule they set
SETTING_KINDS = {
    "madd_monfasel_len": ("madd_monfasel",),
    "madd_mottasel_len": ("madd_mottasel",),
    "madd_mottasel_waqf": ("madd_mottasel_waqf",),
    "madd_aared_len": ("madd_aared",),
    "madd_alleen_len": ("madd_leen",),
    "madd_yaa_alayn_alharfy": ("madd_alayn",),
    "meem_mokhfah": ("iqlab", "ikhfa_shafawi"),
    "ghonna_lam_and_raa": ("idgham_no_ghunnah",),
}
SETTING_SURA = {"harakat_daaf": 30}  # its label: «ضعف» in al-Rum
SETTING_AYAT = {"meem_aal_imran": ((3, 1), (3, 2))}
# «يَسْرِ» (89:4), «أَنْ أَسْرِ» (20:77, 26:52), «فَأَسْرِ» (11:81, 15:65, 44:23): its label
RAA_YASR = ((89, 4), (20, 77), (26, 52), (11, 81), (15, 65), (44, 23))
RAA_YASR_WORD = re.compile("^(ف?أسر|يسر)$")
SETTING_EXAMPLES = 2
# settings about a stop on the word: shown read with that stop
SETTING_STOP = {"alif_salasila", "yaa_ataan"}
# settings that are not tajweed rules: quran-transcript declares them but its phonetizer never
# reads them, so they change nothing in the analysis. Left off the page (the user, 2026-10-16)
NOT_TAJWEED = {"recitation_speed", "takbeer", "saken_before_hamz"}


def item(id_: str, title: str, status: str, source: str, **parts: Iterable[Any]) -> Item:
    """One line to review; `parts` are body (paragraphs), facts (label, value) and examples."""
    return {
        "id": id_,
        "title": title,
        "status": status,
        "source": source,
        "body": list(parts.get("body", ())),
        "facts": [list(f) for f in parts.get("facts", ())],
        "examples": list(parts.get("examples", ())),
    }


def section(key: str, items: list[Item]) -> dict[str, Any]:
    title, intro = W.SECTIONS[key]
    return {"id": key, "title": title, "intro": intro, "items": items}


def hit_examples(found: Found, kinds: Iterable[str], n: int) -> list[dict[str, Any]]:
    out = []
    for kind in kinds:
        for h in spread(found.get(kind, []), n):
            out.append(example(load_ayah(h.sura, h.aya), h.start, h.end))
    return out


# --- reading settings -------------------------------------------------------------------------


def engine_choices(name: str) -> list[R.Value]:
    """All the values the phonetizer has for a setting, before the rules narrow them."""
    out: list[R.Value] = []
    for arg in get_args(MoshafAttributes.model_fields[name].annotation):
        out.extend(get_args(arg) or ([] if arg is type(None) else [arg]))
    return out


def choice_label(value: R.Value, labels: dict[Any, str]) -> str:
    return harakat(value) if isinstance(value, int) else labels.get(value, str(value))


def _pattern_examples(name: str) -> list[dict[str, Any]]:
    cases = [c for c in alph.uthmani.special_patterns if c.attr_name == name]
    sura_only = SETTING_SURA.get(name)
    if sura_only:
        cases = [c for c in cases if c.sura_idx == sura_only] or cases
    out: list[dict[str, Any]] = []
    for s in surah_list():
        if sura_only and s.index != sura_only:
            continue
        for a in range(1, s.ayat + 1):
            text = " ".join(ayah_words(s.index, a))
            for m in (m for case in cases for m in re.finditer(case.pattern, text)):
                out.append(_match_example(name, s.index, a, text, m))
    return out


def _match_example(name: str, sura: int, aya: int, text: str, m: re.Match[str]) -> dict[str, Any]:
    if name in SETTING_STOP:
        return word_example(sura, aya, text.count(" ", 0, m.start()), stop=True)
    return example(load_ayah(sura, aya), m.start(), m.end())


def _boundary_examples(name: str) -> list[dict[str, Any]]:
    out = []
    for (s, a, w), b in sorted(special_boundaries().items()):
        if b.attr != name:
            continue
        ay = load_ayah(s, a)
        last = min(w + 1, len(ay.words) - 1)
        start, end = ay.word_span(w, last)
        out.append(example(ay, start, end))
        if w == len(ay.words) - 1:  # the boundary is the ayah's end: show where it goes on
            out.append(opening_example(s, a + 1))
    return out


def _raa_yasr() -> list[dict[str, Any]]:
    out = []
    for s, a in RAA_YASR:
        words = ayah_words(s, a)
        for w, word in enumerate(words):
            if RAA_YASR_WORD.match("".join(ch for ch in word if ch.isalpha())):
                out.append(word_example(s, a, w, stop=True))
    return out


def setting_examples(name: str, found: Found) -> list[dict[str, Any]]:
    if name in RAA_PLACES:
        keep = RAA_PLACES[name]
        places = [b for b in R.DEFAULT.both_valid if b.letter == R.RAA and keep(b)]
        return [word_example(b.sura, b.aya, b.word or 0, stop=b.when == "stop") for b in places]
    if name in SETTING_KINDS:
        return hit_examples(found, SETTING_KINDS[name], SETTING_EXAMPLES)
    if name in SETTING_AYAT:
        return [ayah_example(s, a) for s, a in SETTING_AYAT[name]]
    if name == "raa_yasr":
        return _raa_yasr()
    if name == "between_anfal_and_tawba":
        last = len(ayah_words(8, 75)) - 1
        return [word_example(8, 75, last), ayah_example(9, 1)]
    return _boundary_examples(name) or _pattern_examples(name)


def _status(name: str) -> str:
    if name in R.FROM_SOURCES:
        return "sources"
    if name in R.DEFAULT.fixed:
        return "fixed"
    return "ruled" if name in R.DEFAULT.allowed else "unreviewed"


def _setting_facts(name: str, choices: list[R.Value], default: R.Value) -> list[tuple[str, str]]:
    info = MoshafAttributes.model_fields[name]
    labels = get_arabic_attributes(info) or {}
    if name in R.DEFAULT.fixed:
        return [(W.FACT_FIXED, choice_label(R.DEFAULT.fixed[name], labels))]
    facts = [
        (W.FACT_CHOICES, "، ".join(choice_label(c, labels) for c in choices)),
        (W.FACT_DEFAULT, choice_label(default, labels)),
    ]
    excluded = [c for c in engine_choices(name) if c not in choices]
    if excluded:
        facts.append((W.FACT_EXCLUDED, "، ".join(choice_label(c, labels) for c in excluded)))
    return facts


def _setting_item(name: str, choices: list[R.Value], default: R.Value, found: Found) -> Item:
    label = " ".join((get_arabic_name(MoshafAttributes.model_fields[name]) or name).split())
    status = _status(name)
    note = W.SETTING_NOTES.get(name) if status != "unreviewed" else W.UNREVIEWED_NOTE
    return item(
        f"setting.{name}",
        label,
        status,
        f"rules.py: {name}",
        body=[note] if note else [],
        facts=_setting_facts(name, choices, default),
        examples=setting_examples(name, found),
    )


def settings_section(found: Found) -> dict[str, Any]:
    options: list[ReadingOption] = moshaf_all_options()
    items = [
        _setting_item(o.name, o.choices, o.default, found)
        for o in options
        if o.name not in NOT_TAJWEED
    ]
    for name, value in R.DEFAULT.fixed.items():
        if name not in NOT_TAJWEED:
            items.append(_setting_item(name, [value], value, found))
    return section("settings", items)


# --- madd lengths and pairs -------------------------------------------------------------------


def combos_section() -> dict[str, Any]:
    pairs = sorted(R.DEFAULT.madd_pairs)
    title, note = W.COMBOS["madd_pairs"]
    items = [
        item(
            "combo.madd_pairs",
            title,
            "ruled",
            "rules.py: madd_pairs",
            body=[note],
            facts=[
                (f"الوجه {ar_num(i + 1)}", f"المنفصل {harakat(a)}، والمتصل {harakat(b)}")
                for i, (a, b) in enumerate(pairs)
            ],
        )  # fmt: skip
    ]
    ruled = {"Monfasel Madd", "Mottasel Madd", "Mottasel Madd at Pause"}
    for rule, lengths in R.DEFAULT.madd_lengths.items():
        status = "ruled" if rule in ruled else "unreviewed"
        body = [W.MADD_LENGTH_NOTE] + ([] if status == "ruled" else [W.MADD_LENGTH_UNRULED])
        items.append(
            item(
                f"madd_lengths.{rule}",
                W.MADD_LENGTH_NAMES[rule],
                status,
                f"rules.py: madd_lengths[{rule!r}]",
                body=body,
                facts=[(W.FACT_CHOICES, "، ".join(harakat(n) for n in lengths))],
            )
        )
    title, note = W.COMBOS["connected_alternatives.sakt_maleeyah"]
    items.append(
        item(
            "connected_alternatives.sakt_maleeyah",
            title,
            "ruled",
            "rules.py: connected_alternatives",
            body=[note],
            examples=_boundary_examples("sakt_maleeyah"),
        )
    )
    return section("combos", items)


# --- both-valid places, raum ------------------------------------------------------------------


def _both_valid_kind(b: R.BothValid) -> str:
    if b.sura == 0:
        return "meem"
    if b.sura == 49:
        return "ism"
    return {54: "nudhur", 26: "firq", 34: "qitr"}.get(b.sura, "misr")


def _both_valid_item(b: R.BothValid, found: Found) -> Item:
    kind = _both_valid_kind(b)
    if kind == "meem":
        return item(
            "both_valid.meem",
            W.BOTH_VALID_MEEM_TITLE,
            "ruled",
            "rules.py: both_valid (meem)",
            body=[W.BOTH_VALID_NOTES["meem"]],
            examples=hit_examples(found, ("iqlab", "ikhfa_shafawi"), SETTING_EXAMPLES),
        )
    words = ayah_words(b.sura, b.aya)
    w = b.word if b.word is not None else _ism_word(words)
    return item(
        f"both_valid.{b.sura}.{b.aya}.{w}",
        W.BOTH_VALID_TITLE.format(word=words[w], ref=ref_ar(b.sura, b.aya)),
        "ruled",
        f"rules.py: both_valid {b.sura}:{b.aya}",
        body=[W.BOTH_VALID_NOTES[kind]],
        examples=[word_example(b.sura, b.aya, w, stop=b.when == "stop")],
    )


def _ism_word(words: tuple[str, ...]) -> int:
    case = next(c for c in alph.uthmani.special_patterns if c.attr_name == "start_with_ism")
    return next(i for i, word in enumerate(words) if case.pattern in word)


def both_valid_section(found: Found) -> dict[str, Any]:
    return section("both_valid", [_both_valid_item(b, found) for b in R.DEFAULT.both_valid])


def practices_section() -> dict[str, Any]:
    title, body = W.RAUM
    on = "مُفعّل" if R.DEFAULT.practices["raum"] else "مُطفأ"
    return section(
        "practices",
        [
            item(
                "practice.raum",
                title,
                "ruled",
                "rules.py: practices",
                body=body,
                facts=[(W.FACT_DEFAULT, on)],
            )
        ],
    )


def judging_section() -> dict[str, Any]:
    items = [
        item(f"judging.{key}", title, "app", "docs/model-and-analysis.md", body=body)
        for key, title, body in W.JUDGING
    ]
    return section("judging", items)
