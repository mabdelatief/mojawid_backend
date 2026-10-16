"""The analysis engine, ported from tajweed_ai's muaalem_lab (the reference; keep its behaviour).

- `engine.text`: Quran text, reading rules, structure, the expected reading and tajweed
  colours. No torch: used by both the API and the worker.
- `engine.pipeline` (phase 4): audio → result. Worker only.
"""
