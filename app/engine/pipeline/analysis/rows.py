"""One error row per difference quran-transcript's explain_error reports.

Ported from tajweed_ai `muaalem_lab/analysis.py` (_rules, _is_false_alarm, _ghunnah,
_valid_variant, _error_row). explain_error has no ghunnah rule, so a held ghunnah heard at the
wrong length is named here.

New in Mojawid (user's decision, 2026-10-16): "unexpected", a ghunnah held on a sakin noon or meem
where none is due (a meem sakin hummed at a stop, or hidden where izhar is due). explain_error
calls it an inserted letter, the most serious kind; it is a tajweed mistake.

Fixed in Mojawid (audit 2026-10-16): a madd row is a false alarm only when expected and heard differ
in the madd letters' count alone, so a missing sakt (idraj at «مَّرْقَدِنَا») or a stray haraka
after a madd is no longer hidden (R3); "unexpected" only for a sakin noon/meem (C3); a clear noon
where ikhfa is due is izhar whatever its length (C4).
"""

from typing import Any

from app.engine.pipeline.analysis.words import Row, word_index
from app.engine.text import rules as RULES
from app.engine.text.qt import alph
from app.engine.text.readable import describe, harakat
from app.engine.text.reference import Reference
from app.engine.text.tajweed import GHUNNAH_HEARD_AS, GHUNNAH_RUN, ghunnah_run, run_length

GHUNNAH_RULE = {
    "ar": "الغنة",
    "en": "Ghunnah",
    "golden_len": None,
    "correctness_type": "count",
    "tag": "ghunnah",
}
GHUNNAH_OPERATION = {
    "short": "delete", "long": "insert", "missing": "replace", "izhar": "replace",
    "unexpected": "insert",
}  # fmt: skip
P = alph.phonetics
HIDDEN_FORM = {P.noon: P.noon_mokhfah, P.meem: P.meem_mokhfah}
# the letters a madd or leen length is written with; what else a madd group holds must match
MADD_RUN_LETTERS = P.alif + P.waw_madd + P.yaa_madd + P.alif_momala + P.waw + P.yaa


def rule_dicts(rules: Any) -> list[dict[str, Any]]:
    return [
        {"ar": r.name.ar, "en": r.name.en, "golden_len": r.golden_len,
         "correctness_type": r.correctness_type, "tag": r.tag}
        for r in (rules or [])
    ]  # fmt: skip


def is_false_alarm(e: Any) -> bool:
    """explain_error emits a tajweed row for any changed group carrying a rule, even when the rule
    was kept. Madd (count) rules: kept if the lengths match. Match rules (qalqalah): kept unless
    the rule is reported missing."""
    if e.error_type != "tajweed" or e.missing_tajweed_rules:
        return False
    if e.expected_len is not None and e.predicted_len is not None:
        return bool(e.expected_len == e.predicted_len) and _rest_equal(e)
    return False


def _rest_equal(e: Any) -> bool:
    """Expected and heard are the same once the madd letters are set aside: nothing else (a sakt,
    a haraka) was lost or added in the group."""
    exp, got = e.expected_ph or "", e.preditected_ph or ""
    strip = str.maketrans("", "", MADD_RUN_LETTERS)
    return exp.translate(strip) == got.translate(strip)


def unexpected_ghunnah(exp: str, got: str) -> bool:
    """A sakin noon or meem expected (no haraka), heard held as a ghunnah or hidden."""
    if exp not in HIDDEN_FORM:
        return False
    return run_length(got, exp) >= GHUNNAH_RUN or run_length(got, HIDDEN_FORM[exp]) >= 1


def ghunnah_state(e: Any, uthmani: str) -> str | None:
    """ "short", "long", "missing" or "izhar" when the reference group is a held ghunnah and the
    run heard differs; "unexpected" for a ghunnah where none is due; None otherwise."""
    exp, got = e.expected_ph, e.preditected_ph
    if not got or e.ref_tajweed_rules:
        return None
    want = ghunnah_run(exp, uthmani)
    if not want:
        return "unexpected" if unexpected_ghunnah(exp, got) else None
    if exp[0] == P.noon_mokhfah and run_length(got, P.noon) and not run_length(got, exp[0]):
        return "izhar"  # a clear noon, held or not, where ikhfa or iqlab was due
    clear = GHUNNAH_HEARD_AS.get(exp[0], exp[0])[1:]  # the clear meem of a hidden one
    if clear and run_length(got, clear) == 1 and run_length(got, exp[0]) == 0:
        # a single clear noon or meem where ikhfa or iqlab was due: izhar, not a short ghunnah
        # (the model confuses these often: the paper reports F1 0.45 for ikhfa)
        return "izhar"
    heard = run_length(got, GHUNNAH_HEARD_AS.get(exp[0], exp[0]))
    if heard == want:
        return None
    return "missing" if heard == 0 else "short" if heard < want else "long"


# the 'ayn of كهيعص / عسق: tagged "Leen Madd" by the phonetizer, but a lazim harfi, 4 or 6 via
# al-Shatibiyya («وفي عين الوجهان والطول فضلا»), never leen's 2 (audit 2026-10-16, R8)
AYN_HARFI = alph.uthmani.ayn + alph.uthmani.madd
AYN_LENGTHS = (4, 6)


def _madd_variant(e: Any, rules: list[Any], uthmani: str = "") -> dict[str, str] | None:
    allowed = dict(RULES.DEFAULT.madd_lengths)
    if AYN_HARFI in uthmani:
        allowed["Leen Madd"] = AYN_LENGTHS
    if e.error_type != "tajweed" or e.predicted_len is None:
        return None
    for r in rules:
        name = r.name.en
        if name in allowed:
            # explain_error's lengths are already harakat, a leen madd included (3 letters → 4).
            # Fixed in Mojawid 2026-10-16 (user's decision): the lab adds 1 for leen again, so
            # it called a leen at the allowed 2 or 6 harakat a mistake and one at 3 allowed.
            heard = e.predicted_len
            if heard in allowed[name] and e.predicted_len != e.expected_len:
                return {
                    "reason": "madd_length",
                    "ar": f"طول جائز ({harakat(heard)})، يختلف عن الإعداد المختار",
                }
    return None


def valid_variant(e: Any, rules: list[Any], uthmani: str = "") -> dict[str, str] | None:
    """A difference that is another correct way to read (the rules table), not a mistake: a madd
    at another allowed length, or the meem of iqlab / ikhfa shafawi read with the lips closed
    instead of a slight gap (or the reverse)."""
    madd = _madd_variant(e, rules, uthmani)
    if madd:
        return madd
    exp, got = e.expected_ph, e.preditected_ph
    mm, m = alph.phonetics.meem_mokhfah, alph.phonetics.meem
    if exp and got and len(exp) == len(got) >= 3 and {exp, got} == {mm * len(exp), m * len(exp)}:
        return {
            "reason": "meem_form",
            "ar": "الميم بإطباق الشفتين أو بفرجة يسيرة: كلاهما صحيح مع الغنة",
        }
    return None


def _is_leen(rules: Any) -> bool:
    return any(r.name.en == "Leen Madd" for r in rules or [])


def _rules_from_reference(e: Any, ref: Reference) -> list[Any]:
    """explain_error marks a deleted group "tajweed" when the reference has a rule there but
    doesn't attach the rule; take it from the reference mappings."""
    seen, rules = set(), []
    for m in ref.phonetic.mappings[e.uthmani_pos[0] : e.uthmani_pos[1]]:
        for r in m.tajweed_rules or []:
            if r.name.en not in seen:
                seen.add(r.name.en)
                rules.append(r)
    return rules


def error_row(i: int, e: Any, ref: Reference, span: tuple[int, int]) -> Row:
    """The report row for one explain_error difference."""
    s, t = span
    ghunnah = ghunnah_state(e, ref.uthmani[s:t])
    rules = e.ref_tajweed_rules
    if e.error_type == "tajweed" and not rules:
        rules = _rules_from_reference(e, ref)
    row: Row = {
        "id": i, "error_type": e.error_type, "operation": e.speech_error_type,
        "uthmani_pos": list(e.uthmani_pos), "uthmani_span": [s, t],
        "uthmani_text": ref.uthmani[s:t], "word_index": word_index(ref.uthmani, e.uthmani_pos[0]),
        "segment": ref.segment_at(e.uthmani_pos[0]), "ph_pos": list(e.ph_pos),
        "expected_ph": e.expected_ph, "predicted_ph": e.preditected_ph,  # sic, upstream spelling
        "expected_text": describe(e.expected_ph, leen=_is_leen(rules)),
        "heard_text": describe(e.preditected_ph, leen=_is_leen(rules)),
        "expected_len": e.expected_len, "predicted_len": e.predicted_len,
        "rules": rule_dicts(rules), "inserted_rules": rule_dicts(e.inserted_tajweed_rules),
        "replaced_rules": rule_dicts(e.replaced_tajweed_rules),
        "missing_rules": rule_dicts(e.missing_tajweed_rules),
        "likely_false_alarm": is_false_alarm(e), "valid_variant": None, "ghunnah": ghunnah,
    }  # fmt: skip
    variant = valid_variant(e, rules, ref.uthmani[s:t])
    if variant and not row["likely_false_alarm"]:
        row.update(valid_variant=variant, likely_false_alarm=True)
    if ghunnah:
        row.update(error_type="tajweed", operation=GHUNNAH_OPERATION[ghunnah],
                   rules=[dict(GHUNNAH_RULE)], likely_false_alarm=False)  # fmt: skip
    return row
