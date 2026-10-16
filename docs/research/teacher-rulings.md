# The teacher's rulings (recorded in the lab, 2026-10-13 and 2026-10-14)

These are the rulings the app follows for Hafs 'an 'Asim via al-Shatibiyya. The app is public;
these answers were given by a licensed teacher, relayed by the user, one question at a time, in the
lab session of 2026-10-13 and in a second round on 2026-10-14. The answers below are quoted as
given, in the user's words. Where a published source disagreed (سلاسلا), the user's instruction
was «اسمع كلامي بس و خلينا نكمل باقي الاسئلة»: the ruling stands. «كل اللي انا بقولهولك ده حفص
الشاطبية» — every answer is for Hafs via al-Shatibiyya.

Encoded in `app/engine/text/rules.py` (ported from tajweed_ai `muaalem_lab/rules.py`); the
source transcript is the lab session of 2026-10-13/14 (tajweed_ai `docs/project-log.md` §11.2
summarises it).

| # | Question (as asked) | Answer (quoted) | Encoded as | Applied by the engine today? |
|---|---|---|---|---|
| 1 | «سَلَـٰسِلَا۟» (الإنسان ٤) at a stop: with or without the alif? | «الالف الاخير في سلاسلا دي من الالفات السبع … مع الوقف عليها بننطق الالف كاملة و مع الوصل الالف بتستخبى». Follow-up, is stopping without it a mistake? «لا لو وقف على سلاسلا بدون الف يبقى خطأ» | `fixed.alif_salasila = ithbat` | Yes |
| 2 | «ءَاتَىٰنِۦَ» (النمل ٣٦) at a stop | «تنطق عند الوقف اتانيي بياء ممدودة» (without it is a mistake) | `fixed.yaa_ataan = ithbat` | Yes |
| 3 | Starting with «ٱلِٱسْمُ» (الحجرات ١١) | «الأسم او لسم — بس ده اصلا اسمه بدء قبيح عشان مش المفروض نبدأ هنا» | `allowed.start_with_ism`, `both_valid` (pronunciation) | **No**: the both-valid entry is never read by the analysis; starting with «لِسْمُ» while the setting is «أَلِسْمُ» is flagged (`docs/research/phonetizer.md` §e) |
| 4 | Sakt at عِوَجَا، مَّرْقَدِنَا، مَنْ رَاقٍ، بَلْ رَانَ: obligatory when connecting? A stop allowed instead at all four? | «اه و اه، في الاربعة». Follow-up: only these four places, not connected reading in general | `allowed.sakt_* = (sakt, waqf)`; idraj excluded | **Partly**: idraj at «مَّرْقَدِنَا» (36:52) is not counted (`tools/research/findings.py idraj`); at 75:27 and 83:14 it is counted, but named as a missing letter plus a haraka mistake |
| 5 | Munfasil and muttasil: allowed lengths; qasr of munfasil; munfasil 5 with muttasil 4 | «٤ و ٤ / اه يحسب خطأ / اه يحسب خطأ». Follow-up: «٥ و ٥ مش غلط / ٤ منفصل و ٥ متصل مش غلط / و اخر سوال ج ده، يجوز» (muttasil at a stop on a final hamza: 4/5/6) | `allowed.madd_*`, `madd_pairs = {(4,4),(5,5),(4,5)}`, `madd_lengths` | **Partly**: settings refuse 5/4, but what is *heard* is judged one madd at a time, so munfasil 5 with muttasil 4 is shown as allowed (`findings.py madd_pairs`) |
| 6 | Meem of iqlab and ikhfa shafawi: lips closed or a slight gap | «يصح بس فيها خلاف» — both, with the ghunnah held | `allowed.meem_mokhfah`, `valid_variant` meem form | Yes |
| 7 | «وَنُذُرِ» (القمر) at a stop | «يجوز الاتنين، تفخيم او ترقيق» | `both_valid` (raa, 6 places) | Yes |
| 8 | «فِرْقٍ» (الشعراء ٦٣) | «يجوز اه في الوصل بس لكن في الوقف الحكم يكون التفخيم» | `both_valid` connected; the phonetizer gives tafkheem at a stop | Yes |
| 9 | «مِصْرَ» at a stop (2026-10-14, Q1) | «الوجهان جائزان و التفخيم مقدم» | `both_valid` + `defaults.raa_misr = tafkheem` | Yes (needs our phonetizer patch 2) |
| 10 | «ٱلْقِطْرِ» at a stop (Q2) | «الوجهان جائزان و الترقيق مقدم» | `both_valid` + `defaults.raa_alqitr = tarqeeq` | Yes (patch 2) |
| 11 | «مَالِيَهْ ۜ هَلَكَ» (Q3) | «أصلا هنا رأس ايه فيجوز الوقف و يجوز السكت عند حفص و يجوز الإدغام كمان» | `allowed.sakt_maleeyah`, `connected_alternatives` | Yes |
| 12 | Between al-Anfal and al-Tawba (Q4) | «كله جائز» | `allowed.between_anfal_and_tawba` | Yes (never met in a test yet) |
| 13 | Raum at a stop (Q5) | «يحسب صح و لكن رايي خليه اختياري لاننا مش بنقرأ بيه بس بنتعلمه للاجازه و لازم نفرق بين حد قاصد و بيقرا بيه و حد مش بيتم الحروف في نهاية الكلمات فخليه اختيار يفعله القاري لو عاوز يتدرب عليه» | `practices.raum = False` (an option) | Yes |

## What the rulings don't cover

Everything below is decided from the Shatibiyya sources (`shatibiyya-sources.md`) under the
product rule (2026-10-16): **the app accepts exactly what Hafs via al-Shatibiyya allows; an option
only al-Tayyiba allows is removed, even if it sounds harmless.** Points the sources leave
genuinely open are listed in `README.md` ("Still for the teacher").
