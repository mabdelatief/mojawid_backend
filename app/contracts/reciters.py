"""Reciters and their word timings."""

from typing import Literal

from pydantic import BaseModel, Field

Style = Literal["murattal", "mujawwad", "muallim"]


class Reciter(BaseModel):
    """A reciter the app can offer: every one has word-by-word timings."""

    slug: str = Field(examples=["husary"])
    name_ar: str
    name_en: str
    style: Style
    audio_url_template: str = Field(
        description="Ayah audio URL with {surah:03d} and {ayah:03d} placeholders.",
        examples=[
            "https://verseaudiofiles.eu-central-1.linodeobjects.com/Husary_64kbps/{surah:03d}{ayah:03d}.mp3"
        ],
    )


class ReciterList(BaseModel):
    """The reciters offered, and which one is the default."""

    default: str
    reciters: list[Reciter]


class AyahTiming(BaseModel):
    """One ayah's audio and where each word is in it."""

    surah: int
    ayah: int
    audio_url: str
    segments: list[tuple[int, int, int, int]] = Field(
        description=(
            "[first_word, last_word, start_ms, end_ms]. Word indexes are 0-based and inclusive "
            "into the ayah's words; a segment over several words is a merged span (a tap on any "
            "of them plays the span). A word in no segment isn't tappable for this reciter."
        )
    )


class ReciterTimings(BaseModel):
    """Timings for a run of ayat in one surah."""

    reciter: str
    ayat: list[AyahTiming]
