"""The pipeline side of the engine: a recording → the result. Worker only.

torch is imported only by `doubt.py` and `models/` (the GPU part). The API never imports this
package (tests/unit/test_import_boundaries.py).
"""
