import streamlit as st
from quran_transcript import Aya, search

if __name__ == "__main__":
    search_text = st.text_input('نص البحث')
    search_button = st.button('ابحث')
    winodw = st.number_input('النافذة', value=2)

    if search_button:
        start_aya = Aya('quran-script/quran-uthmani-imlaey-map.json', 1, 1)
        results = search(
            start_aya,
            search_text,
            window=winodw,
            ignore_hamazat=True,
            ignore_alef_maksoora=True,
            ignore_haa_motatrefa=True,
            ignore_taa_marboota=True,
            ignore_small_alef=True,
            ignore_tashkeel=True,
        )

        for result in results:
            st.write(f'{result}')
            st.write('-' * 10)
