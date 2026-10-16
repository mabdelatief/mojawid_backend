"""Notes on a result that aren't mistakes.

Ported from tajweed_ai `muaalem_lab/collect_api.py` (_cut_in_speech, the warnings in _result).
Each has a stable code (the app shows its own text by code) and Arabic text. The lab's over-30 s
note told teachers to trim the clip before reviewing; Mojawid's tells the reciter what it means.
"""

from typing import Any

from app.engine.pipeline.pauses import Pauses

SOFT_MAX_SECONDS = 30.0  # the model was trained on clips of at most 30 s

CUT_IN_SPEECH_AR = "يبدو أن التسجيل {} أثناء التلاوة؛ قد تكون كلمة مقطوعة، فلا تُحسب خطأً."
EDGE_AR = {"start": "يبدأ", "end": "ينتهي"}
OVER_30S_AR = "التسجيل أطول من ٣٠ ثانية؛ تدرّب النموذج على مقاطع أقصر، فقد تقل الدقة."


def cut_in_speech(pauses: Pauses | None) -> list[str]:
    """Which ends of a clip fall while the reciter is speaking."""
    if pauses is None:
        return []
    edges = (("start", pauses.starts_in_speech), ("end", pauses.ends_in_speech))
    return [e for e, hit in edges if hit]


def warnings(pauses: Pauses | None, duration_s: float) -> list[dict[str, Any]]:
    """The result's warnings: the clip starts/ends mid-recitation, and it is over 30 s."""
    out: list[dict[str, Any]] = []
    edges = cut_in_speech(pauses)
    if edges:
        out.append(
            {
                "code": "cut_in_speech",
                "edges": edges,
                "message_ar": CUT_IN_SPEECH_AR.format(" و".join(EDGE_AR[e] for e in edges)),
            }
        )
    if duration_s > SOFT_MAX_SECONDS:
        out.append({"code": "over_30s", "edges": [], "message_ar": OVER_30S_AR})
    return out
