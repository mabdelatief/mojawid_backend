"""L1 goldens: on the lab's own model outputs, the port's pipeline gives exactly the lab's result.

tests/golden/pipeline/ holds, per case, tajweed_ai's frame probabilities (all 11 outputs), the
segmenter's frame labels, and the result its `/test` flow gave (tools/golden/make_pipeline_golden,
run in the lab's environment on the GPU). Here the port decodes those same probabilities and runs
the whole CPU side: the heard script, the detection, the path, the report and the warnings must
match. Fields new to Mojawid (not in the lab) are set aside first: the sifat `allowed` flag and the
error rows' extras. Decoding the same probabilities means GPU noise can't hide a porting bug.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.engine.pipeline.decode import decode
from app.engine.pipeline.errors import AnalysisError
from app.engine.pipeline.heard import Heard
from app.engine.pipeline.pauses import SAMPLE_RATE, pauses_from_labels
from app.engine.pipeline.run import Job, Outcome, analyse
from app.engine.text.structure import TextSelection

GOLDEN = Path(__file__).resolve().parents[2] / "golden" / "pipeline"
CASES = sorted(p for p in GOLDEN.glob("*.json") if p.name != "vocab.json")
NEW_ROW_KEYS = (
    "key",
    "mark",
    "counted",
    "sura",
    "aya",
    "word",
    "expected_harakat",
    "heard_harakat",
)
# Mojawid pairs the sifat table by its own alignment of whole letter groups (audit 2026-10-16,
# C1): the lab's pairing matched a letter with its neighbour. It gives the lab's rows exactly on
# every golden except a recording of another text, where any pairing of unrelated letters is
# arbitrary; there only the coverage is checked (every expected and heard letter exactly once).
SIFAT_PAIRING_DIFFERS = {"wrong_text_manual"}


def _vocab() -> tuple[dict[str, dict[int, str]], dict[str, dict[int, str]]]:
    raw = json.loads((GOLDEN / "vocab.json").read_text())
    as_int = {k: {int(i): v for i, v in m.items()} for k, m in raw["id_to_vocab"].items()}
    sifat = {k: {int(i): v for i, v in m.items()} for k, m in raw["sifat_to_en_vocab"].items()}
    return as_int, sifat


def heard_for(golden: dict[str, Any]) -> Heard:
    data = np.load(GOLDEN / f"{golden['case']['id']}.npz")
    probs = {k: data[k] for k in data.files if k != "segmenter_labels"}
    id_to_vocab, sifat_to_en = _vocab()
    heard = decode(probs, id_to_vocab, sifat_to_en)
    heard.pauses = pauses_from_labels(data["segmenter_labels"], golden["n_samples"])
    return heard


def job_for(case: dict[str, Any]) -> Job:
    t = case["text"]
    text = (
        None
        if t is None
        else TextSelection(t["sura"], t["aya_start"], t["aya_end"], prefixes=tuple(t["prefixes"]))
    )
    return Job(text=text, reading=case["reading"], raum=case["raum"])


def plain(value: Any) -> Any:
    """As the golden JSON has it (tuples become lists)."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=list))


def without_new_fields(report: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = copy.deepcopy(plain(report))
    for row in out["sifat"]:
        for attr in row["attrs"].values():
            attr.pop("allowed", None)
    for row in out["errors"]:
        for k in NEW_ROW_KEYS:
            row.pop(k, None)
    for seg in out["segments"]:
        for word in seg["words"]:
            word.pop("waqf", None)  # the Mushaf's waqf signs, for display (2026-10-17)
    return out


def outcome_for(golden: dict[str, Any]) -> Outcome:
    return analyse(job_for(golden["case"]), heard_for(golden), golden["n_samples"] / SAMPLE_RATE)


@pytest.fixture(params=CASES, ids=lambda p: p.stem)
def golden(request: pytest.FixtureRequest) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(Path(request.param).read_text())
    return data


def test_goldens_present() -> None:
    assert len(CASES) >= 20, "run tools/golden/make_pipeline_golden in tajweed_ai's environment"


def test_heard_script_and_frames(golden: dict[str, Any]) -> None:
    heard = heard_for(golden)
    assert heard.text == golden["heard"]
    assert plain(heard.group_frames) == golden["group_frames"]


def test_result_matches_the_lab(golden: dict[str, Any]) -> None:
    if golden["error"]:
        with pytest.raises(AnalysisError) as err:
            outcome_for(golden)
        assert err.value.code == golden["error"]
        return
    outcome = outcome_for(golden)
    assert plain(outcome.text.__dict__)["sura"] == golden["text"]["sura"]
    assert (outcome.text.aya_start, outcome.text.aya_end) == (
        golden["text"]["aya_start"],
        golden["text"]["aya_end"],
    )
    assert list(outcome.text.prefixes) == golden["text"]["prefixes"]
    assert plain(outcome.detection) == golden["detection"]
    assert plain(outcome.path) == golden["path"]
    ours, theirs = without_new_fields(outcome.report), golden["report"]
    assert theirs.pop("sifat_unreliable_probs") == []  # dropped in the port: always empty here
    if golden["case"]["id"] in SIFAT_PAIRING_DIFFERS:
        assert_covers(ours["sifat"], theirs.pop("sifat"))
        ours.pop("sifat")
    for key in theirs:
        assert ours[key] == theirs[key], key
    assert set(ours) == set(theirs)


def assert_covers(ours: list[dict[str, Any]], theirs: list[dict[str, Any]]) -> None:
    """Both tables hold every expected letter and every heard letter exactly once, in order."""
    for side in ("ref", "pred"):
        assert [r[side] for r in ours if r[side]] == [r[side] for r in theirs if r[side]], side


def test_warnings(golden: dict[str, Any]) -> None:
    if golden["error"]:
        return
    outcome = outcome_for(golden)
    edges = [e for e in ("start", "end") if golden["pauses"][f"{e}s_in_speech"]]
    codes = [w["code"] for w in outcome.warnings]
    assert ("cut_in_speech" in codes) == bool(edges)
    assert ("over_30s" in codes) == (golden["n_samples"] / SAMPLE_RATE > 30)
