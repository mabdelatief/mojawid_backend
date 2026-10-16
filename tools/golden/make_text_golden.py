"""Make the text goldens: tajweed_ai's own references for ~200 selections, to check the port
(app.engine.text) against. Runs in tajweed_ai's environment, from this repo's root:

    uv run --project ../tajweed_ai python -m tools.golden.make_text_golden [--lab ../tajweed_ai]

Writes tests/golden/references.json (committed). The cases are fixed by a seed, so re-running on
an unchanged lab gives the same file.
"""

import argparse
import importlib
import json
import pathlib
import random
import sys
from typing import Any

from tools.golden.summary import summarize

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = REPO / "tests" / "golden" / "references.json"
SEED = 20261016

READING_VARIANTS: list[dict[str, Any]] = [
    {"madd_monfasel_len": 5, "madd_mottasel_len": 5},
    {"madd_monfasel_len": 4, "madd_mottasel_len": 5},
    {"madd_mottasel_waqf": 6},
    {"madd_aared_len": 2},
    {"madd_aared_len": 6, "madd_alleen_len": 6},
    {"meem_mokhfah": "meem"},
    {"raa_misr": "tarqeeq", "raa_alqitr": "tafkheem"},
    {"recitation_speed": "hadr"},
    {"sakt_iwaja": "waqf", "sakt_marqdena": "sakt", "sakt_man_raq": "waqf", "sakt_bal_ran": "waqf"},
    {"sakt_maleeyah": "idgham"},
]
PREFIXES = [(), (), ("istiaatha",), ("basmala",), ("istiaatha", "basmala")]


def _random_cases(surahs: list[dict[str, Any]], rng: random.Random, n: int) -> list[dict[str, Any]]:
    cases = []
    for _ in range(n):
        s = rng.choice(surahs)
        start = rng.randint(1, s["ayat"])
        end = min(s["ayat"], start + rng.choice([0, 0, 1, 2]))
        reading = rng.choice(READING_VARIANTS) if rng.random() < 0.25 else {}
        cases.append(
            {"sura": s["index"], "aya_start": start, "aya_end": end,
             "prefixes": list(rng.choice(PREFIXES)), "reading": reading}
        )  # fmt: skip
    return cases


def _boundary_cases(quran: Any, surahs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every special-boundary ayah, alone and joined to the next, with the default reading and
    with every allowed choice at that boundary."""
    cases = []
    for (sura, aya, _), sb in sorted(quran.special_boundaries().items()):
        end = min(aya + 1, surahs[sura - 1]["ayat"])
        for choice in [None, *sb.options]:
            reading = {} if choice is None else {sb.attr: choice}
            for aya_end in sorted({aya, end}):
                cases.append(
                    {"sura": sura, "aya_start": aya, "aya_end": aya_end, "prefixes": [],
                     "reading": reading}
                )  # fmt: skip
    return cases


FIXED_CASES: list[dict[str, Any]] = [
    {"sura": 1, "aya_start": 1, "aya_end": 7, "prefixes": ["istiaatha", "basmala"], "reading": {}},
    {"sura": 9, "aya_start": 1, "aya_end": 2, "prefixes": ["istiaatha"], "reading": {}},
    {"sura": 2, "aya_start": 255, "aya_end": 255, "prefixes": [], "reading": {}},
    {"sura": 76, "aya_start": 4, "aya_end": 4, "prefixes": [], "reading": {}},
    {"sura": 27, "aya_start": 36, "aya_end": 36, "prefixes": [], "reading": {}},
    {"sura": 112, "aya_start": 1, "aya_end": 4, "prefixes": ["basmala"], "reading": {}},
]


def _build(lab: dict[str, Any], case: dict[str, Any]) -> dict[str, Any] | None:
    quran, tajweed = lab["quran"], lab["tajweed"]
    try:
        moshaf = quran.moshaf_from_dict(case["reading"])
        ref = quran.build_reference(
            case["sura"], case["aya_start"], moshaf, case["aya_end"], case["prefixes"]
        )
    except ValueError:
        return None  # a reading the rules refuse: not a golden
    return {
        "case": case,
        "expected": summarize(ref, tajweed.tajweed_spans(ref.uthmani, ref.phonetic)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lab", type=pathlib.Path, default=REPO.parent / "tajweed_ai")
    args = parser.parse_args()
    sys.path.append(str(args.lab.resolve()))
    lab = {m: importlib.import_module(f"muaalem_lab.{m}") for m in ("quran", "tajweed")}
    surahs = lab["quran"].surah_list()
    cases = FIXED_CASES + _boundary_cases(lab["quran"], surahs)
    cases += _random_cases(surahs, random.Random(SEED), 150)
    built = [g for g in (_build(lab, c) for c in cases) if g is not None]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(built, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {len(built)} goldens ({len(cases) - len(built)} refused readings skipped)")


if __name__ == "__main__":
    main()
