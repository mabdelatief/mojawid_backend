"""The model snapshots every analysis is made with: the one place model ids and revisions live
(CLAUDE.md; enforced by the discipline scan, which holds the same two revisions).

A new upstream revision changes what the model hears, so it is only taken on purpose: download
it, check it against the goldens, then change it here, in CLAUDE.md and in the scanner together.
"""

import dataclasses


@dataclasses.dataclass(frozen=True)
class ModelPin:
    repo_id: str
    revision: str


MUAALEM = ModelPin("obadx/muaalem-model-v3_2", "01a1ef9fbe40d144ef845101e89ff924aed3fef5")
SEGMENTER = ModelPin("obadx/recitation-segmenter-v2", "5ee90364e7090ea6eb9dffe80353bed06996a196")
