"""The local folder of a pinned model snapshot. Loading from a folder never contacts the hub."""

import os
from pathlib import Path

from app.model_pins import ModelPin


def hub_cache() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    home = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface")
    return home / "hub"


def model_path(pin: ModelPin) -> Path:
    """The snapshot folder; FileNotFoundError (with the download command) if it isn't there."""
    path = hub_cache() / f"models--{pin.repo_id.replace('/', '--')}" / "snapshots" / pin.revision
    if not (path / "config.json").exists():
        raise FileNotFoundError(
            f"Model snapshot {pin.revision} of {pin.repo_id} is not in {hub_cache()}. Download it "
            f"once with `huggingface-cli download {pin.repo_id} --revision {pin.revision}`."
        )
    return path
