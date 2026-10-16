import time
import sys
from quran_transcript import Aya, normalize_aya, search, WordSpan


if __name__ == "__main__":
    # TODO: add these tests in pytest
    # -------------------------------------------------------------------
    # Test General Use
    # -------------------------------------------------------------------
    # start_aya = Aya(
    #     1, 1, quran_path='quran-script/quran-uthmani-imlaey-map.json')
    # start_aya.set(114, 2)
    # # print(start_aya.get())
    # start = time.time()
    # for idx, aya in enumerate(start_aya.get_ayat_after()):
    #     print(aya.get())
    # print('idx', idx)
    # print(f'Total Time: {time.time() - start:f}')
    # print(start_aya)

    # -------------------------------------------------------------------
    # Test Looping
    # -------------------------------------------------------------------
    # start_aya = Aya(
    #     114, 5, quran_path='quran-script/quran-uthmani-imlaey-map.json')
    # for idx, aya in enumerate(start_aya.get_ayat_after(num_ayat=10)):
    #     print(aya)
    #     print(idx)

    # -------------------------------------------------------------------
    # Test set rasm
    # -------------------------------------------------------------------
    # start_aya = Aya(
    #     113, 1, quran_path='quran-script/quran-uthmani-imlaey-map.json')
    #
    # print('Before: ')
    # print(start_aya.get())
    #
    # uthmani_list = [[word] for word in start_aya.get().uthmani.split()]
    # imlaey_list = [[word] for word in start_aya.get().imlaey.split()]
    # start_aya.set_rasm_map(uthmani_list, imlaey_list)
    #
    # print('After: ')
    # print(start_aya.get())

    # -------------------------------------------------------------------
    # Test General Step
    # -------------------------------------------------------------------
    # start_aya = Aya(
    #     114, 1, quran_path='quran-script/quran-uthmani-imlaey-map.json')
    # steps = [0, 1, 293, 493, 292, -1, -2, -11]
    # # steps = [-1]
    # for step in steps:
    #     print(f'Step={step}')
    #     print(start_aya.step(step))
    #     print('#' * 30)

    # -------------------------------------------------------------------
    # Test get_fromatted_rasmp_map
    # -------------------------------------------------------------------
    # aya = Aya(
    #     111, 1, quran_path='quran-script/quran-uthmani-imlaey-map.json')
    # print(aya.get_formatted_rasm_map())

    # -------------------------------------------------------------------
    # Test set_new
    # -------------------------------------------------------------------
    # aya = Aya(
    #     111, 1, quran_path='quran-script/quran-uthmani-imlaey-map.json')
    # new_aya = aya.set_new(4, 4)
    # print('OLD AYA')
    # print(aya)
    # print()
    # print('NEW AYA')
    # print(new_aya)

    # -------------------------------------------------------------------
    # Test normaliz text
    # -------------------------------------------------------------------
    # aya = Aya(
    #     111, 1, quran_path='quran-script/quran-uthmani-imlaey-map.json')
    # norm_aya = normalize_aya(
    #     aya.get().imlaey,
    #     remove_spaces=True,
    #     ignore_hamazat=True,
    #     ignore_alef_maksoora=True,
    #     ignore_taa_marboota=False,
    #     normalize_taat=False,
    #     remove_small_alef=True,
    #     remove_tashkeel=True,
    # )
    # print(aya.get().imlaey)
    # print(norm_aya)

    # -------------------------------------------------------------------
    # Test search
    # -------------------------------------------------------------------
    # start_aya = Aya('quran-script/quran-uthmani-imlaey-map.json', 1, 1)
    start_aya = Aya(1, 1)
    # search_aya = start_aya.set_new(1, 7)
    # search_text = "الحمد لله"
    # search_text = "وأن لو"
    # search_text = "إياك"
    # search_text = "من إفكهم ليقولون ولد الله وإنهم لكاذبون"
    # search_text = "الرحيم الحمد لله"
    search_text = "وَالضُّحَى  وَاللَّيْلِ إِذَا سَجَى  مَا وَدَّعَكَ رَبُّكَ وَمَا قَلَى  وَلَلْآخِرَةُ خَيْرٌ لَكَ مِنَ الْأُولَى  وَلَسَوْفَ يُعْطِيكَ رَبُّكَ فَتَرْضَى  أَلَمْ يَجِدْكَ يَتِيمًا فَآوَى  وَوَجَدَكَ ضَالًّا فَهَدَى  وَوَجَدَكَ"
    # search_text = "وَمَثَلُ كَلِمَةٍ خَبِيثَةٍ كَشَجَرَةٍ خَبِيثَةٍ اجْتُثَّتْ مِنْ فَوْقِ الْأَرْضِ مَا لَهَا مِنْ قَرَارٍ"
    # search_text = "بسم الله الرحمن الرحيم والضحى"
    # search_text = 'ولم يكن له كفوا أحد'
    # search_text = "أعوذ بالله من الشيطان الرجيم بسم الله الرحمن الرحيم"
    # search_text = "أعوذ بالله من الشيطان الرجيم براءة  من الله ورسوله"
    # search_text = 'بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ'
    # search_text = "ثُمَّ عَفَوْنَا عَنْكُمْ مِنْ بَعْدِ ذَلِكَ لَعَلَّكُمْ تَشْكُرُونَ"
    # search_text = "أعوذ بالله من الشيطان الرجيم"
    # search_text = 'test'
    start_time = time.time()
    results = search(
        search_text,
        # start_aya=start_aya,
        window=6236,
        ignore_hamazat=False,
        ignore_alef_maksoora=False,
        ignore_taa_marboota=False,
        normalize_taat=False,
        remove_small_alef=True,
        remove_tashkeel=True,
    )
    end_time = time.time()
    count = 0
    for item in results:
        print(item)
        print("-" * 20)
        count += 1
    print("Total Results:", count)
    print("Total Time:", end_time - start_time)

    # -------------------------------------------------------------------
    # Test _encode_imlaey_to_uthmani
    # -------------------------------------------------------------------
    # aya = Aya(
    #     1, 5, quran_path='quran-script/quran-uthmani-imlaey-map.json')
    # print(aya)
    # print(aya._encode_imlaey_to_uthmani())

    # -------------------------------------------------------------------
    # Test _encode_imlaey_to_uthmani
    # -------------------------------------------------------------------
    # # aya = Aya('quran-script/quran-uthmani-imlaey-map.json', 72, 16)
    # aya = Aya(
    #     72, 16, quran_path='quran-script/quran-uthmani-imlaey-map.json')
    # span = WordSpan(0, 7)
    # print(aya.imlaey_to_uthmani(span))
