"""Download brain tumor classifier weights from Hugging Face."""

from __future__ import annotations

import os
from pathlib import Path

_HF_REPO = "ThisenEkanayake/brain-tumor-detection"
_HF_FILENAME = "multiclass-classification/multi_class_resnet.pth"


def ensure_model_checkpoint(output_path: str) -> str:
    """Download ResNet18 weights if missing; return local path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size > 1_000_000:
        return str(path)

    from huggingface_hub import hf_hub_download

    cached = hf_hub_download(
        repo_id=_HF_REPO,
        filename=_HF_FILENAME,
        local_dir=str(path.parent),
        local_dir_use_symlinks=False,
    )
    cached_path = Path(cached)
    if cached_path.resolve() != path.resolve():
        if path.is_file():
            path.unlink()
        os.replace(cached, path)
    return str(path)
