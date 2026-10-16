"""Reading settings (quran-transcript's MoshafAttributes) under the rules table.

Ported from tajweed_ai `muaalem_lab/quran.py` (moshaf_* and build_moshaf). The old
`moshaf_options` (the lab dashboard's short list) is dropped.
"""

import dataclasses
from collections.abc import Mapping
from typing import Any, get_args

from app.engine.text import rules as R
from app.engine.text.qt import MoshafAttributes, get_arabic_attributes, get_arabic_name

# The madd fields; madd_alleen_len defaults to madd_aared_len.
MOSHAF_FIELDS = [
    "madd_monfasel_len",
    "madd_mottasel_len",
    "madd_mottasel_waqf",
    "madd_aared_len",
    "madd_alleen_len",
]

# quran-transcript has no Hafs preset; these are the values the upstream Muaalem Gradio app, docs
# and tests use.
HAFS_DEFAULTS = {
    "madd_monfasel_len": 4,
    "madd_mottasel_len": 4,
    "madd_mottasel_waqf": 4,
    "madd_aared_len": 4,
}

# Settings shown first; the rest sit under "more reading choices".
MAIN_READING_FIELDS = [*MOSHAF_FIELDS, "recitation_speed", "meem_mokhfah", "madd_yaa_alayn_alharfy"]


@dataclasses.dataclass(frozen=True)
class ReadingOption:
    """One reading setting a reciter may choose, with its allowed values and Arabic labels."""

    name: str
    label_ar: str
    choice_labels_ar: Mapping[Any, str]
    choices: list[R.Value]
    default: R.Value
    main: bool


def _as_int(value: object) -> int:
    """int(value), as the lab does, for the types a setting arrives as."""
    if isinstance(value, int | float | str):
        return int(value)
    raise ValueError(f"not a number: {value!r}")


def allowed_choices(name: str) -> list[R.Value]:
    """A MoshafAttributes field's values that the rules allow."""
    info = MoshafAttributes.model_fields[name]
    choices: list[R.Value] = []
    for arg in get_args(info.annotation):
        choices.extend(get_args(arg) or ([] if arg is type(None) else [arg]))
    allowed = R.DEFAULT.allowed.get(name)
    return [c for c in choices if allowed is None or c in allowed]


def build_moshaf(values: Mapping[str, object] | None = None) -> Any:
    """The Hafs defaults, with the rules' defaults and fixed settings, plus any madd fields
    given. ValueError if the combination isn't allowed."""
    params: dict[str, object] = dict(HAFS_DEFAULTS)
    for k, v in (values or {}).items():
        if k in MOSHAF_FIELDS and v is not None and v != "":
            params[k] = _as_int(v)
    problems = R.DEFAULT.check_moshaf(params)
    if problems:
        raise ValueError("; ".join(problems))
    return MoshafAttributes(rewaya="hafs", **params, **R.DEFAULT.defaults, **R.DEFAULT.fixed)


def moshaf_all_options() -> list[ReadingOption]:
    """The reading settings a reciter may choose under the rules, with Arabic labels and the
    Hafs defaults. Settings the rules fix are not offered."""
    defaults = build_moshaf().model_dump()
    out = []
    for name, info in MoshafAttributes.model_fields.items():
        if name == "rewaya" or name in R.DEFAULT.fixed:
            continue
        out.append(
            ReadingOption(
                name=name,
                label_ar=get_arabic_name(info) or name,
                choice_labels_ar=get_arabic_attributes(info) or {},
                choices=allowed_choices(name),
                default=defaults[name],
                main=name in MAIN_READING_FIELDS,
            )
        )
    return out


def _accepts(key: str, value: object, stored: bool) -> bool:
    """Whether a submitted setting is taken (unknown keys, rewaya and empty values never are;
    fixed settings only when reading back stored ones)."""
    fields = MoshafAttributes.model_fields
    if not stored and key in R.DEFAULT.defaults and value == fields[key].default:
        # the phonetizer's own default, saved by recordings made before the rules chose one
        # (e.g. raa_alqitr "wasl"): not a choice anyone made, so the rules' default applies
        return False
    if key not in fields or key == "rewaya" or value is None or value == "":
        return False
    return stored or key not in R.DEFAULT.fixed


def moshaf_from_dict(values: Mapping[str, object] | None, stored: bool = False) -> Any:
    """A full MoshafAttributes from a reciter's choices (unknown keys ignored).

    New choices follow the rules: its fixed settings always apply, and a choice it doesn't allow
    is a ValueError (pydantic's ValidationError, a ValueError, for a value the field can't take).
    `stored=True` reads back saved settings exactly as saved."""
    base: dict[str, object] = build_moshaf().model_dump(exclude={"madd_alleen_len"})
    for k, v in (values or {}).items():
        if _accepts(k, v, stored):
            is_int = isinstance(base.get(k), int) or k.startswith("madd_")
            base[k] = _as_int(v) if is_int else v
    if not stored:
        problems = R.DEFAULT.check_moshaf(base)
        if problems:
            raise ValueError("; ".join(problems))
    return MoshafAttributes(**{**base, "rewaya": "hafs"})
