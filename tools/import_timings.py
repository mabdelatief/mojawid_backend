# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["quran-transcript==0.6.4+muaalem.1"]
#
# [tool.uv.sources]
# quran-transcript = { path = "../../tajweed_ai/vendor/quran-transcript" }
# ///
"""One-time import of the reciters' word timings, re-keyed to our own words.

Source: cpfair/quran-align, release 2016-11-24 (CC-BY 4.0). These are the same timings
quran.com serves for these recitations: identical on all 6,930 ayat compared (10 surahs x 9
recitations, 2026-10-15). Its words are Tanzil's Uthmani text split on spaces, which is what
quran-transcript gives us, so the word indexes carry over unchanged.

Output, in OUT_DIR:
  <slug>.json     {"recitation": {...}, "ayat": {"s:a": [[first_word, last_word, start_ms, end_ms], ...]}}
                  word indexes 0-based and inclusive; ms into that ayah's mp3 in our bucket
  coverage.json   per recitation: words with their own timing, in merged spans, without timing,
                  dropped segments by reason, repaired ayat (to be checked by ear)

Runtime never reads cpfair or quran.com: these files are loaded into our Postgres
(tools/load_timings.py) and the audio is served from our bucket.

    uv run tools/import_timings.py OUT_DIR [--cache DIR]
"""

import argparse
import hashlib
import json
import pathlib
import urllib.request
import zipfile

from quran_transcript import Aya

RELEASE_URL = ("https://github.com/cpfair/quran-align/releases/download/"
               "release-2016-11-24/quran-align-data-2016-11-24.zip")
RELEASE_SHA1 = "6fcd48c0f8320ed1ae5fef58184a3924ae1fd264"

# The recitations Mojawid offers. AbdulBaset Mujawwad and Minshawi Mujawwad stay in the bucket
# but are not offered: 2.4 % of their words have no timing of their own.
RECITATIONS = [
    # slug, name_ar, name_en, style, bucket prefix, cpfair file, quran.com id, file sha1
    ("abdulbaset-murattal", "عبد الباسط عبد الصمد", "AbdulBaset AbdulSamad", "murattal",
     "AbdulBaset/Murattal/mp3/", "Abdul_Basit_Murattal_64kbps", 2,
     "029e32d2cdc869e2f33ae86fd21214952d18f33d"),
    ("sudais", "عبد الرحمن السديس", "Abdur-Rahman as-Sudais", "murattal",
     "Sudais/mp3/", "Abdurrahmaan_As-Sudais_192kbps", 3,
     "4315194bc88db14192201426fb4f6617bffac4ac"),
    ("shatri", "أبو بكر الشاطري", "Abu Bakr al-Shatri", "murattal",
     "Shatri/mp3/", "Abu_Bakr_Ash-Shaatree_128kbps", 4,
     "8861fadb68bad84ae5189227e0bcdd7a7127e976"),
    ("rifai", "هاني الرفاعي", "Hani ar-Rifai", "murattal",
     "Rifai/mp3/", "Hani_Rifai_192kbps", 5,
     "22e0cea40ff434848295f8ce959ab885292ebb7b"),
    ("husary", "محمود خليل الحصري", "Mahmoud Khalil al-Husary", "murattal",
     "Husary_64kbps/", "Husary_64kbps", 6,
     "8e7a24f66f98f176dfddf65b434643a6655c694d"),
    ("minshawi-murattal", "محمد صديق المنشاوي", "Mohamed Siddiq al-Minshawi", "murattal",
     "Minshawi/Murattal/mp3/", "Minshawy_Murattal_128kbps", 9,
     "2a24d42e7f3a018c56600fc4ddd580f214b20a39"),
    ("shuraym", "سعود الشريم", "Sa'ud ash-Shuraym", "murattal",
     "Shuraym/mp3/", "Saood_ash-Shuraym_128kbps", 10,
     "59fd80d144caa6fe79a917a8d1dddf18087b3bcc"),
    ("tablawi", "محمد محمود الطبلاوي", "Mohamed al-Tablawi", "murattal",
     "Mohammad_al_Tablaway_128kbps/", "Mohammad_al_Tablaway_128kbps", 11,
     "dce92289eebd76380d1dae22f2329493a49f06db"),
    ("husary-muallim", "محمود خليل الحصري", "Mahmoud Khalil al-Husary", "muallim",
     "Husary_Muallim_128kbps/", "Husary_Muallim_128kbps", 12,
     "b03e6c9188934504b6921d22b1f2e2b72ee773eb"),
]


def our_words() -> dict[tuple[int, int], int]:
    """(surah, ayah) -> number of words, the way the analysis splits them."""
    aya = Aya(1, 1)
    counts = {}
    for s in range(1, 115):
        aya.set(s, 1)
        for a in range(1, aya.get().num_ayat_in_sura + 1):
            aya.set(s, a)
            counts[(s, a)] = len(aya.get().uthmani.split(" "))
    return counts


def fetch_release(cache: pathlib.Path) -> zipfile.ZipFile:
    path = cache / "quran-align-data-2016-11-24.zip"
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(RELEASE_URL, headers={"User-Agent": "mojawid-import"})
        with urllib.request.urlopen(req, timeout=120) as r:
            path.write_bytes(r.read())
    if hashlib.sha1(path.read_bytes()).hexdigest() != RELEASE_SHA1:
        raise SystemExit(f"{path}: checksum mismatch")
    return zipfile.ZipFile(path)


def load_file(z: zipfile.ZipFile, name: str, sha1: str) -> list[dict]:
    raw = z.read(f"{name}.json")
    if hashlib.sha1(raw).hexdigest() != sha1:
        raise SystemExit(f"{name}: checksum mismatch")
    text = raw.decode()
    # The Sudais file starts with a stray crash-log line from cpfair's own run.
    start = 0 if text.startswith("[") else text.index("\n[") + 1
    return json.loads(text[start:])


def repair_shift(segs: list[list[int]], n: int) -> list[list[int]] | None:
    """In some ayat that open with separate letters (الٓر، الٓمٓر …) cpfair skips one index
    after the letters, so every later segment points one word too far and the last one past
    the end. Shift the segments after the gap back, but only when that exactly fills it."""
    over = max(j for _, j, _, _ in segs) - n
    covered = {w for i, j, _, _ in segs for w in range(i, j)}
    gap = next((w for w in range(n) if w not in covered), None)
    if over <= 0 or gap is None:
        return None
    shifted = [[i - over, j - over, a, b] for i, j, a, b in segs if i >= gap]
    if any(i < gap for i, _, _, _ in shifted):
        return None
    out = [s for s in segs if s[0] < gap] + shifted
    words = [w for i, j, _, _ in out for w in range(i, j)]
    if max(words) >= n or len(words) != len(set(words)):
        return None
    return out


def import_one(entries: list[dict], counts: dict[tuple[int, int], int]):
    ayat, stats = {}, {"words": 0, "own_timing": 0, "in_merged_span": 0, "no_timing": 0,
                       "dropped": {"zero_or_negative_length": 0, "past_last_word": 0},
                       "repaired_ayat": [], "ayat_without_timing": []}
    seen = set()
    for e in entries:
        key = (e["surah"], e["ayah"])
        seen.add(key)
        n = counts[key]
        segs = sorted([int(x) for x in s[:4]] for s in e.get("segments") or [])
        if segs and max(j for _, j, _, _ in segs) > n:
            fixed = repair_shift(segs, n)
            if fixed is not None:
                segs = fixed
                stats["repaired_ayat"].append(f"{key[0]}:{key[1]}")
            else:
                stats["dropped"]["past_last_word"] += sum(1 for _, j, _, _ in segs if j > n)
                segs = [s for s in segs if s[1] <= n]
        good = []
        for i, j, a, b in segs:
            if b <= a or j <= i:
                stats["dropped"]["zero_or_negative_length"] += 1
            else:
                good.append([i, j - 1, a, b])  # inclusive last word from here on
        if not good:
            stats["ayat_without_timing"].append(f"{key[0]}:{key[1]}")
        timed = {}
        for i, last, _, _ in good:
            for w in range(i, last + 1):
                timed[w] = last > i
        stats["words"] += n
        stats["own_timing"] += sum(1 for w in range(n) if timed.get(w) is False)
        stats["in_merged_span"] += sum(1 for w in range(n) if timed.get(w) is True)
        stats["no_timing"] += sum(1 for w in range(n) if w not in timed)
        ayat[f"{key[0]}:{key[1]}"] = good
    if seen != set(counts):
        raise SystemExit(f"ayat missing from the source: {len(set(counts) - seen)}")
    return ayat, stats


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out_dir", type=pathlib.Path)
    p.add_argument("--cache", type=pathlib.Path, default=pathlib.Path(".cache/quran-align"))
    args = p.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    counts = our_words()
    z = fetch_release(args.cache)
    coverage = {}
    for slug, name_ar, name_en, style, prefix, cp_name, qcom_id, sha1 in RECITATIONS:
        ayat, stats = import_one(load_file(z, cp_name, sha1), counts)
        recitation = {"slug": slug, "name_ar": name_ar, "name_en": name_en, "style": style,
                      "bucket_prefix": prefix, "file_pattern": "{surah:03d}{ayah:03d}.mp3",
                      "timing_source": f"cpfair/quran-align 2016-11-24 {cp_name} (CC-BY 4.0)",
                      "quran_com_recitation_id": qcom_id}
        (args.out_dir / f"{slug}.json").write_text(
            json.dumps({"recitation": recitation, "ayat": ayat}, ensure_ascii=False, separators=(",", ":")))
        coverage[slug] = stats
        print(f"{slug:20s} words={stats['words']} own={stats['own_timing']} "
              f"merged={stats['in_merged_span']} none={stats['no_timing']} "
              f"dropped={stats['dropped']} repaired={len(stats['repaired_ayat'])}")
    (args.out_dir / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
