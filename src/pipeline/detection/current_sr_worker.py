"""Generate one current x4 SR image without loading HOMR or CNN models."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import cv2

from src.common.preprocessing import apply_advanced_sr
from src.pipeline.utils.images import load_image


def _load_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Current-SR request must be a mapping")
    return dict(payload)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(request_path: Path, result_path: Path) -> Path:
    request = _load_request(request_path)
    det_cfg = request.get("detection")
    if not isinstance(det_cfg, Mapping):
        raise ValueError("Current-SR request lacks detection settings")

    image = Path(str(request["image"])).resolve()
    output = Path(str(request["output"])).resolve()
    if not image.is_file():
        raise FileNotFoundError(image)

    sr_scale = int(det_cfg.get("sr_scale", 2))
    if sr_scale != 4:
        raise ValueError(f"Verified Stage E current SR requires sr_scale=4, got {sr_scale}")

    image_bgr = load_image(image, None)
    upscaled, _upsampler = apply_advanced_sr(
        image_bgr,
        model_name="RealESRGAN_x4plus",
        scale=4,
        tile=det_cfg.get("sr_tile", -1),
        tile_pad=int(det_cfg.get("sr_tile_pad", 10)),
        fp32=bool(det_cfg.get("sr_fp32", False)),
        upsampler=None,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), upscaled):
        raise RuntimeError(f"Failed to write current x4 SR image: {output}")

    payload = {
        "schema_version": "pipeline.current_x4_sr.v1",
        "status": "completed",
        "image": str(image),
        "sr_scale": 4,
        "sr_image": str(output),
        "sr_sha256": _sha256(output),
        "historical_detector_artifact_runtime_input": False,
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.request, args.result)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"status": "completed", "result": str(result)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
