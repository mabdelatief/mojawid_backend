"""One-time import of the Mushaf's waqf signs onto our words.

Our Quran text is Tanzil's Uthmani 1.1 edition without pause, sajda and hizb marks (bundled by
quran-transcript). Tanzil's full edition of the same text has the signs, each as its own token
after the word it belongs to. Its words match ours in every ayah once the small iqlab/tanween
meem (U+06E2, U+06ED) is set aside: the two editions place it differently. Any other difference
stops the run.

Output: app/engine/text/data/waqf_signs.json
  {"source": "...", "signs": {"<sura>:<aya>:<word>": "<sign characters, in order>"}}
with word indexes 0-based over our words (app.engine.text.quran_text.ayah_words). Runtime never
reads Tanzil; only this file.

    .venv/bin/python -m tools.import_waqf_signs [--xml quran-uthmani.xml]

Source and licence (Tanzil's notice, reproduced as its terms ask):

    Tanzil Quran Text (Uthmani, Version 1.1)
    Copyright (C) 2007-2026 Tanzil Project
    License: Creative Commons Attribution 3.0

    This copy of the Quran text is carefully produced, highly verified and continuously
    monitored by a group of specialists at Tanzil Project.

    TERMS OF USE:
    - Permission is granted to copy and distribute verbatim copies of this text, but CHANGING
      IT IS NOT ALLOWED.
    - This Quran text can be used in any website or application, provided that its source
      (Tanzil Project) is clearly indicated, and a link is made to tanzil.net to enable users to
      keep track of changes.
    - This copyright notice shall be included in all verbatim copies of the text, and shall be
      reproduced appropriately in all files derived from or containing substantial portion of
      this text.

    Please check updates at: http://tanzil.net/updates/
"""

import argparse
import collections
import json
import pathlib
import urllib.request
import xml.etree.ElementTree as ET

from app.engine.text.quran_text import ayah_words

URL = (
    "https://tanzil.net/pub/download/index.php?marks=true&sajdah=true&rub=true&tatweel=true"
    "&quranType=uthmani&outType=xml&agree=true"
)
OUT = pathlib.Path("app/engine/text/data/waqf_signs.json")
SIGNS = frozenset(chr(c) for c in range(0x06D6, 0x06DD))  # صلى قلى ۘ ج لا ∴ and the sakt seen
NOT_WORDS = SIGNS | {"۞", "۩"}  # plus the hizb and sajda marks, not imported
MEEMS = str.maketrans("", "", "ۭۢ")
SOURCE = (
    "Tanzil Quran Text (Uthmani, Version 1.1), Copyright (C) 2007-2026 Tanzil Project, "
    "Creative Commons Attribution 3.0. Only the waqf signs are taken, attached to the word they "
    "follow; see tools/import_waqf_signs.py."
)


def _is_mark(token: str) -> bool:
    return bool(token) and all(c in NOT_WORDS for c in token)


def ayah_signs(text: str) -> tuple[list[str], dict[int, str]]:
    """Tanzil's words for one ayah, and the signs after each word (by word index)."""
    words: list[str] = []
    signs: dict[int, str] = collections.defaultdict(str)
    for token in text.split(" "):
        if not _is_mark(token):
            words.append(token)
        elif words:  # a hizb mark opens an ayah; signs always follow a word
            signs[len(words) - 1] += "".join(c for c in token if c in SIGNS)
    return words, {k: v for k, v in signs.items() if v}


def collect(root: ET.Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for sura in root:
        for aya in sura:
            s, a = int(sura.attrib["index"]), int(aya.attrib["index"])
            words, signs = ayah_signs(aya.attrib["text"])
            ours = [w.translate(MEEMS) for w in ayah_words(s, a)]
            if [w.translate(MEEMS) for w in words] != ours:
                raise SystemExit(f"{s}:{a}: Tanzil's words don't match ours; nothing written")
            out.update({f"{s}:{a}:{w}": sign for w, sign in signs.items()})
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--xml", type=pathlib.Path, help="a downloaded copy instead of fetching")
    args = p.parse_args()
    raw = args.xml.read_bytes() if args.xml else urllib.request.urlopen(URL, timeout=60).read()
    signs = collect(ET.fromstring(raw))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = {"source": SOURCE, "signs": signs}
    OUT.write_text(json.dumps(body, ensure_ascii=False, indent=0, sort_keys=True) + "\n")
    totals = collections.Counter(c for v in signs.values() for c in v)
    print(f"{len(signs)} words with a sign -> {OUT}")
    print({f"U+{ord(k):04X}": n for k, n in sorted(totals.items())})


if __name__ == "__main__":
    main()
