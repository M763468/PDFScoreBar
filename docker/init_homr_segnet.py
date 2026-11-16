"""Materialize only the HOMR SegNet model used by PDFScoreBar (Issue #533).

``python -m homr.main --init`` always downloads the transformer checkpoint
(Run 426, trained with PrIMuS and MuseTrainer according to upstream
Training.md). PDFScoreBar consumes only SegNet barlines and masks, so the image
ships the fp16 SegNet alone and fails the build if the bytes differ or a
transformer checkpoint is present.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from homr import download_utils
from homr.segmentation import config as segnet_config
from homr.title_detection import download_ocr_weights

RELEASE_URL = "https://github.com/liebharc/homr/releases/download/onnx_checkpoints/"
# SHA-256 of the extracted ONNX, matching the #504 audit of the 426/308 image.
EXPECTED_SEGNET_FP16_SHA256 = "60f495496cb41473c0521d0811d8f44b9d5cff892d287974a8aebb3eaee2fa83"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    model = Path(segnet_config.segnet_path_onnx_fp16)
    if not model.is_file():
        base_name = model.name.split(".")[0]
        zip_path = model.parent / f"{base_name}.zip"
        try:
            download_utils.download_file(f"{RELEASE_URL}{base_name}.zip", str(zip_path))
            download_utils.unzip_file(str(zip_path), str(model.parent))
        finally:
            if zip_path.exists():
                zip_path.unlink()
    actual = _sha256(model)
    if actual != EXPECTED_SEGNET_FP16_SHA256:
        print(f"SegNet fp16 hash mismatch: {model} {actual}", file=sys.stderr)
        return 1
    # Keep HOMR's OCR initialization from the previous --init step.
    download_ocr_weights()
    transformer_dir = Path(segnet_config.__file__).resolve().parents[1] / "transformer"
    leftovers = sorted(p.name for p in transformer_dir.glob("*.onnx"))
    if leftovers:
        print(f"Transformer checkpoints must not be shipped: {leftovers}", file=sys.stderr)
        return 1
    print(f"SegNet ready: {model.name} sha256={actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
