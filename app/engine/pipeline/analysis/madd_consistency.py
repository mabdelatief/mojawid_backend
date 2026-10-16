"""Madd lengths judged across the whole recording, not one place at a time (audit 2026-10-16, R1 and
R2; docs/research/shatibiyya-sources.md #19–20).

A madd heard at another allowed length is a valid variant on its own (rows.valid_variant). But the
teacher ruled munfasil 5 with muttasil 4 a mistake (rules.madd_pairs), and Hidayat al-Qari requires
taswiya: one length for a kind of madd throughout a reading, and a leen at a stop never longer
than the 'arid. So, per recording:

- **The reciter's length for each kind** (munfasil, connected muttasil, 'arid, leen) is the
  setting's length if any place of that kind was read at it, otherwise the length heard most.
- **Taswiya:** an allowed-length row whose length differs from it becomes a mistake.
- **The pair:** when munfasil and muttasil both occur and their lengths aren't an allowed pair,
  the rows that differ from the setting become mistakes.
- **Leen:** a leen row longer than the reciter's 'arid becomes a mistake.

The changed rows carry `consistency_ar`, the reason in Arabic.
"""

import collections
import dataclasses

from app.engine.pipeline.analysis.words import Row
from app.engine.text import rules as R
from app.engine.text.groups import RefGroup, ref_groups
from app.engine.text.qt import alph
from app.engine.text.readable import harakat
from app.engine.text.reference import Reference

KINDS = ("Monfasel Madd", "Mottasel Madd", "Aared Madd", "Leen Madd")
NAME_AR = {
    "Monfasel Madd": "المد المنفصل",
    "Mottasel Madd": "المد المتصل",
    "Aared Madd": "المد العارض",
    "Leen Madd": "مد اللين",
}
AYN = alph.uthmani.ayn


@dataclasses.dataclass
class Place:
    expected: int
    heard: int
    row: Row | None


def _is_variant(row: Row | None) -> bool:
    v = row.get("valid_variant") if row else None
    return bool(v and v.get("reason") == "madd_length")


def _row_at(rows: list[Row], g: RefGroup, kind: str) -> Row | None:
    for r in rows:
        a, b = r["ph_pos"]
        if a < g.end and g.start < b and any(x["en"] == kind for x in r["rules"]):
            return r
    return None


def _places(rows: list[Row], ref: Reference) -> dict[str, list[Place]]:
    out: dict[str, list[Place]] = collections.defaultdict(list)
    for g in ref_groups(ref):
        kind = next((k for k in KINDS if k in g.rules), None)
        if kind is None or g.kind != "madd" or (kind == "Leen Madd" and g.uth_char == AYN):
            continue  # the 'ayn of كهيعص / عسق is a lazim harfi, judged on its own
        expected = g.count + g.harakat_offset
        row = _row_at(rows, g, kind)
        heard = row["predicted_len"] if row and row.get("predicted_len") is not None else expected
        out[kind].append(Place(expected, heard, row))
    return out


def _chosen(places: list[Place]) -> tuple[int, int]:
    """(the setting's length, the reciter's length)."""
    setting = collections.Counter(p.expected for p in places).most_common(1)[0][0]
    heard = [p.heard for p in places]
    if setting in heard:
        return setting, setting
    return setting, collections.Counter(heard).most_common(1)[0][0]


def _mark(p: Place, reason: str) -> None:
    if p.row is not None and _is_variant(p.row):
        p.row.update(likely_false_alarm=False, valid_variant=None, consistency_ar=reason)


def apply_madd_consistency(rows: list[Row], ref: Reference) -> None:
    places = _places(rows, ref)
    chosen = {k: _chosen(ps) for k, ps in places.items()}
    for kind, ps in places.items():
        setting, length = chosen[kind]
        for p in ps:
            if p.heard != length:
                _mark(p, f"{NAME_AR[kind]} هنا بطول يخالف بقية التلاوة ({harakat(length)})")
    _pair(places, chosen)
    _leen_not_longer(places, chosen)


def _pair(places: dict[str, list[Place]], chosen: dict[str, tuple[int, int]]) -> None:
    if "Monfasel Madd" not in chosen or "Mottasel Madd" not in chosen:
        return
    mon, mut = chosen["Monfasel Madd"][1], chosen["Mottasel Madd"][1]
    if (mon, mut) in R.DEFAULT.madd_pairs:
        return
    reason = f"المنفصل {harakat(mon)} مع المتصل {harakat(mut)}: لا يصح الجمع بينهما"
    for kind in ("Monfasel Madd", "Mottasel Madd"):
        setting = chosen[kind][0]
        for p in places[kind]:
            if p.heard != setting:
                _mark(p, reason)


def _leen_not_longer(places: dict[str, list[Place]], chosen: dict[str, tuple[int, int]]) -> None:
    if "Leen Madd" not in places or "Aared Madd" not in chosen:
        return
    aared = chosen["Aared Madd"][1]
    for p in places["Leen Madd"]:
        if p.heard > aared:
            _mark(p, f"مد اللين لا يزيد على المد العارض ({harakat(aared)})")
