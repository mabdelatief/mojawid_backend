from app.api_utils import (
    get_aya,
    get_suar_names,
    step_ayat,
    get_first_aya_to_annotate,
    save_rasm_map,
    save_quran_dict,
)
import time

if __name__ == "__main__":
    start_time = time.time()
    ayaformat = get_aya(4, 4)
    print('Total time:', time.time() - start_time)
    print(ayaformat)
    print()

    print('Suar Names')
    print(get_suar_names())
    print()

    print('Step ayat')
    print(step_ayat(ayaformat, -10))
    print()

    print('Fistt Aya to Annotate')
    print(get_first_aya_to_annotate())
    print()

    print('Save Rasm Map')
    ayaformat = get_aya(4, 4)
    print(save_rasm_map(
        sura_idx=4,
        aya_idx=4,
        uthmani_words=[[word] for word in ayaformat.uthmani.split(' ')],
        imlaey_words=[[word] for word in ayaformat.imlaey.split(' ')],
    ))
    print()

    print('Save Quran Dict')
    print(save_quran_dict())
    print()
