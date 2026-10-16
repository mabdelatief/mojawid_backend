"""What counts as correct, per riwaya and tareeq: the reading choices a reciter may pick, choices
fixed by the teachers' rulings, and places where more than one way is correct.

Ported unchanged from tajweed_ai `muaalem_lab/rules.py`. Only Hafs 'an 'Asim via al-Shatibiyya
exists for now. Its entries come from the teachers' rulings of 2026-10-13 and 2026-10-14
(tajweed_ai docs/project-log.md, "Teachers' rulings"); they override published sources where the
two differ. Other riwayat are added as further tables here, never as branches in the code that
uses them. Settings fixed or narrowed from al-Shatibiyya's text, before any teacher ruled on them,
are listed in `FROM_SOURCES`; the rest no teacher has ruled on keep the phonetizer's own choices
(`UNREVIEWED`).
"""

import dataclasses
from collections.abc import Mapping

Value = int | str


@dataclasses.dataclass(frozen=True)
class BothValid:
    """A place where two (or more) ways are correct, so neither is a mistake."""

    sura: int
    aya: int
    word: int | None  # index of the word in the ayah; None: every occurrence in the ayah range
    level: str  # the sifa level, or "pronunciation"
    values: tuple[str, ...]
    when: str  # "stop" (the word ends a segment), "connected", "start" or "any"
    note: str
    letter: str | None = None  # the Uthmani letter it covers (e.g. the raa); None: every letter

    def applies(self, at_stop: bool) -> bool:
        """Whether it covers a letter that is (or isn't) at a stop."""
        return (
            self.when == "any"
            or (self.when == "stop" and at_stop)
            or (self.when == "connected" and not at_stop)
        )


@dataclasses.dataclass(frozen=True)
class LetterPlace:
    """Where a letter is: its word, whether that word ends a segment, and the Uthmani letter."""

    sura: int
    aya: int
    word: int
    at_stop: bool
    letter: str | None = None


@dataclasses.dataclass(frozen=True)
class Alternative:
    """A word read more than one correct way whatever the setting (a MoshafAttributes field)."""

    field: str
    values: tuple[str, ...]
    suras: tuple[int, ...] = ()  # only in these suras; empty: anywhere


@dataclasses.dataclass(frozen=True)
class Rules:
    """One riwaya + tareeq."""

    name: str
    # reading settings fixed for everyone (MoshafAttributes field -> value)
    fixed: Mapping[str, Value]
    # reading settings a reciter may choose, and the values allowed (field -> values)
    allowed: Mapping[str, tuple[Value, ...]]
    # allowed (madd_monfasel_len, madd_mottasel_len) pairs
    madd_pairs: frozenset[tuple[int, int]]
    both_valid: tuple[BothValid, ...]
    # madd lengths (harakat) that are all correct for a rule, whatever the chosen setting
    madd_lengths: Mapping[str, tuple[int, ...]] = dataclasses.field(default_factory=dict)
    # the preferred way where more than one is correct: the default reading setting
    defaults: Mapping[str, Value] = dataclasses.field(default_factory=dict)
    # special boundaries where several connected ways are all correct (field -> values): path
    # inference keeps whichever was heard, and none of them is a mistake
    connected_alternatives: Mapping[str, tuple[str, ...]] = dataclasses.field(default_factory=dict)
    # words read two correct ways whatever the setting (field -> values): the analysis keeps the
    # one closest to what was heard, so the other is never flagged
    alternatives: tuple[Alternative, ...] = ()
    # optional practices: correct, but only when the reciter says beforehand they mean it (name ->
    # default). Off, the same sound is taken as a mistake
    practices: Mapping[str, bool] = dataclasses.field(default_factory=dict)

    def both_valid_at(self, level: str, place: "LetterPlace") -> BothValid | None:
        """The both-valid entry covering this letter's sifa level, if any."""
        for b in self.both_valid:
            if b.level != level or (b.sura, b.aya) != (place.sura, place.aya):
                continue
            if b.word is not None and b.word != place.word:
                continue
            if b.letter is not None and place.letter != b.letter:
                continue
            if b.applies(place.at_stop):
                return b
        return None

    def check_moshaf(self, values: Mapping[str, object]) -> list[str]:
        """Why a set of reading settings is not a correct reading under these rules."""
        problems = []
        for field, ok in self.allowed.items():
            if field in values and values[field] not in ok:
                allowed = ", ".join(map(str, ok))
                problems.append(f"{field}={values[field]!r} is not allowed ({allowed})")
        pair = (values.get("madd_monfasel_len"), values.get("madd_mottasel_len"))
        if None not in pair and pair not in self.madd_pairs:
            problems.append(
                f"munfasil {pair[0]} with muttasil {pair[1]} is not a correct combination"
            )
        return problems


# Settings nobody has ruled on yet: the phonetizer's own options stay available.
UNREVIEWED = (
    "madd_aared_len", "madd_alleen_len", "meem_aal_imran", "almusaytirun", "idgham_nakhluqkum",
    "raa_yasr", "recitation_speed",
)  # fmt: skip

# Settings fixed or narrowed from al-Shatibiyya's text, not from a teacher's ruling (audit
# 2026-10-16, docs/research/shatibiyya-sources.md): what only al-Tayyiba gives is removed. They
# wait for the teachers' confirmation.
FROM_SOURCES = (
    "noon_and_yaseen", "yabsut", "bastah", "bimusaytir", "ghonna_lam_and_raa",
    "saken_before_hamz", "takbeer", "yalhath_dhalik", "irkab_maana", "madd_yaa_alayn_alharfy",
    "harakat_daaf", "noon_tamnna", "tasheel_or_madd",
)  # fmt: skip

RAA = "ر"

_RAA_LEVEL = "tafkheem_or_taqeeq"
_RAA_VALUES = ("mofakham", "moraqaq")

HAFS_SHATIBIYYA = Rules(
    name="hafs_shatibiyya",
    fixed={
        # «سَلَـٰسِلَا۟» (76:4): stopped on with the alif; without it is a mistake
        "alif_salasila": "ithbat",
        # «ءَاتَىٰنِۦَ» (27:36): stopped on with the yaa as a madd; without it is a mistake
        "yaa_ataan": "ithbat",
        # from al-Shatibiyya's text (FROM_SOURCES); the other way is al-Tayyiba's only
        # «يسٓ ۝ وَٱلْقُرْءَانِ», «نٓ ۝ وَٱلْقَلَمِ»: the noon is read clearly
        "noon_and_yaseen": "izhar",
        # «وَيَبْصُۜطُ» (2:245), «بَصْۜطَةًۭ» (7:69): with a seen
        "yabsut": "seen",
        "bastah": "seen",
        # «بِمُصَيْطِرٍ» (88:22): with a saad
        "bimusaytir": "saad",
        # no ghunnah when a noon or tanween merges into lam or raa
        "ghonna_lam_and_raa": "no_ghonna",
        # no sakt before a hamza (on al-, shay' or a sakin letter at a word end)
        "saken_before_hamz": "tahqeek",
        # no takbeer is part of the riwaya for Hafs
        "takbeer": "no_takbeer",
    },
    allowed={
        # munfasil and muttasil: (4,4), (5,5) or (4,5); qasr of the munfasil is a mistake
        "madd_monfasel_len": (4, 5),
        "madd_mottasel_len": (4, 5),
        # a stop on a muttasil whose hamza ends the word: 4, 5 or 6
        "madd_mottasel_waqf": (4, 5, 6),
        # sakt at the four places is obligatory when connecting; a stop instead is allowed at all
        # four; connecting without sakt (idraj) is a mistake
        "sakt_iwaja": ("sakt", "waqf"),
        "sakt_marqdena": ("sakt", "waqf"),
        "sakt_man_raq": ("sakt", "waqf"),
        "sakt_bal_ran": ("sakt", "waqf"),
        # the meem of iqlab and ikhfa shafawi: lips closed or a slight gap, both correct
        "meem_mokhfah": ("ikhfaa", "meem"),
        # «فِرْقٍ» connected: both correct (see both_valid); at a stop the phonetizer always gives
        # tafkheem, the only correct way there
        "raa_firq": ("tafkheem", "tarqeeq"),
        # «وَنُذُرِ» at a stop: both correct (see both_valid)
        "raa_nudhur": ("tafkheem", "tarqeeq"),
        # starting with «ٱلِٱسْمُ» (49:11): both correct (see both_valid)
        "start_with_ism": ("alism", "lism", "wasl"),
        # «مِصْرَ» and «ٱلْقِطْرِ» at a stop: tafkheem and tarqeeq both correct (see both_valid);
        # the setting only picks the one shown (2026-10-14)
        "raa_misr": ("tafkheem", "tarqeeq"),
        "raa_alqitr": ("tafkheem", "tarqeeq"),
        # «مَالِيَهْ ۜ هَلَكَ» (69:28-29): an ayah end, so a stop is allowed; connected, sakt and
        # idgham are both correct (2026-10-14)
        "sakt_maleeyah": ("sakt", "waqf", "idgham"),
        # between al-Anfal and al-Tawba: a stop, sakt and wasl are all correct (2026-10-14)
        "between_anfal_and_tawba": ("waqf", "sakt", "wasl"),
        # from al-Shatibiyya's text (FROM_SOURCES): «يَلْهَثْ ذَّٰلِكَ», «ٱرْكَب مَّعَنَا» merged
        # (or a stop between them), never read clearly
        "yalhath_dhalik": ("idgham", "waqf"),
        "irkab_maana": ("idgham", "waqf"),
        # the 'ayn of كهيعص and حمٓ ۝ عٓسٓقٓ: 6 (preferred) or 4
        "madd_yaa_alayn_alharfy": (4, 6),
        # both ways correct whatever the setting (see alternatives); the setting picks the one shown
        "harakat_daaf": ("fath", "dam"),
        "noon_tamnna": ("ishmam", "rawm"),
        "tasheel_or_madd": ("madd", "tasheel"),
        "rewaya": ("hafs",),
    },
    defaults={
        # both correct at a stop; the teachers prefer tafkheem for «مِصْرَ» and tarqeeq for
        # «ٱلْقِطْرِ» (2026-10-14)
        "raa_misr": "tafkheem",
        "raa_alqitr": "tarqeeq",
        "madd_yaa_alayn_alharfy": 6,
    },
    connected_alternatives={
        "sakt_maleeyah": ("sakt", "idgham"),
    },
    alternatives=(
        # al-Shatibiyya gives Hafs both ways in each (docs/research/shatibiyya-sources.md; the
        # teacher's ruling for ٱلِٱسْمُ), so neither is a mistake (audit 2026-10-16, R4 and R9).
        # ضعف only in al-Rum (30:54): in al-Anfal (8:66) Hafs reads fath alone
        Alternative("harakat_daaf", ("fath", "dam"), suras=(30,)),
        Alternative("noon_tamnna", ("ishmam", "rawm")),
        Alternative("tasheel_or_madd", ("madd", "tasheel")),
        Alternative("start_with_ism", ("alism", "lism")),
    ),
    practices={
        # raum at a stop is correct, but the teachers don't read with it: it is learnt for the
        # ijaza. A faint haraka at a stop also comes from not finishing the last letter, a
        # mistake, so raum counts only when the reciter turned this on before reciting
        # (2026-10-14)
        "raum": False,
    },
    madd_pairs=frozenset({(4, 4), (5, 5), (4, 5)}),
    madd_lengths={
        "Monfasel Madd": (4, 5),
        "Mottasel Madd": (4, 5),
        "Mottasel Madd at Pause": (4, 5, 6),
        # 'arid and leen: the phonetizer's 2/4/6 (published sources agree; no teacher ruling yet)
        "Aared Madd": (2, 4, 6),
        "Leen Madd": (2, 4, 6),
    },
    both_valid=(
        *(
            BothValid(54, a, w, _RAA_LEVEL, _RAA_VALUES, "stop",
                      "«وَنُذُرِ» at a stop: tafkheem and tarqeeq of the raa are both correct", RAA)
            for a, w in ((16, 3), (18, 5), (21, 3), (30, 3), (37, 8), (39, 2))
        ),
        BothValid(26, 63, 10, _RAA_LEVEL, _RAA_VALUES, "connected",
                  "«فِرْقٍ» connected: tafkheem and tarqeeq of the raa are both correct", RAA),
        *(
            BothValid(s, a, w, _RAA_LEVEL, _RAA_VALUES, "stop",
                      "«مِصْرَ» at a stop: tafkheem (preferred) and tarqeeq are both correct", RAA)
            for s, a, w in ((10, 87, 7), (12, 21, 4), (12, 99, 9), (43, 51, 9))
        ),
        BothValid(89, 4, 2, _RAA_LEVEL, _RAA_VALUES, "stop",
                  "«يَسْرِ» at a stop: tafkheem and tarqeeq of the raa are both correct", RAA),
        *(
            BothValid(s, a, w, _RAA_LEVEL, _RAA_VALUES, "stop",
                      "«أَسْرِ» at a stop: tafkheem and tarqeeq of the raa are both correct", RAA)
            for s, a, w in ((20, 77, 5), (26, 52, 4), (11, 81, 8), (15, 65, 0), (44, 23, 0))
        ),
        BothValid(34, 12, 9, _RAA_LEVEL, _RAA_VALUES, "stop",
                  "«ٱلْقِطْرِ» at a stop: tarqeeq (preferred) and tafkheem are both correct", RAA),
        BothValid(49, 11, None, "pronunciation", ("alism", "lism"), "start",
                  "starting with «ٱلِٱسْمُ»: «أَلِسْمُ» and «لِسْمُ» are both correct "
                  "(starting there is itself a bad start)"),
        BothValid(0, 0, None, "pronunciation", ("ikhfaa", "meem"), "any",
                  "the meem of iqlab and ikhfa shafawi: lips closed or a slight gap, with the "
                  "ghunnah held"),
    ),
)  # fmt: skip

RULES = {"hafs_shatibiyya": HAFS_SHATIBIYYA}
DEFAULT = HAFS_SHATIBIYYA
