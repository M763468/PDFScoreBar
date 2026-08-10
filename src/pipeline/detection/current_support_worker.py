"""Generate current x4 SR/HOMR/OMR support for one detector page.

The verified Stage E production route keeps the accepted HOMR baseline/SR profile
separate from the current runtime.  This worker supplies only the current x4 image
and current OMR evidence.  It deliberately uses the maintained HybridDetector SR
path that reproduced the Issue #255 full-68 x4 artifact byte-for-byte.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.pipeline.core.subprocess_utils import run_with_logging

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Current-support request must be a mapping")
    return dict(payload)


def run(request_path: Path, result_path: Path) -> Path:
    request = _load_request(request_path)
    det_cfg = request.get("detection")
    if not isinstance(det_cfg, Mapping):
        raise ValueError("Current-support request lacks detection settings")

    image = Path(str(request["image"])).resolve()
    output_root = Path(str(request["output_root"])).resolve()
    if not image.is_file():
        raise FileNotFoundError(image)

    sr_scale = int(det_cfg.get("sr_scale", 2))
    if sr_scale != 4:
        raise ValueError(f"Verified Stage E current support requires sr_scale=4, got {sr_scale}")

    # Import the heavy current detector only inside this disposable worker.
    from src.pipeline.detection.connector_artifacts import (
        install_homr_connector_artifact_capture,
        install_homr_skip_existing_guard,
    )
    from src.pipeline.detection.hybrid import HybridDetector

    install_homr_connector_artifact_capture()
    install_homr_skip_existing_guard(HybridDetector)

    detector = HybridDetector(
        det_cfg=dict(det_cfg),
        images=[image],
        run_id="current_support",
        project_root=PROJECT_ROOT,
        dry_run=False,
        skip_existing=False,
        in_memory_images=None,
    )

    sr_output = output_root / "sr"
    detector._run_homr_in_process(sr_output, enable_sr=True, sr_scale=sr_scale)

    stem = image.stem
    sr_page = sr_output / "batch" / stem
    sr_image = sr_page / image.name
    current_sr_detection = sr_page / f"{stem}_detections.json"
    for required in (sr_image, current_sr_detection):
        if not required.is_file():
            raise FileNotFoundError(required)

    omr_output = output_root / "omr_sr"
    image_arg = detector._rel(image)
    python_cmd_omr = detector._get_python_cmd("omr_dln")
    omr_cmd = python_cmd_omr + [
        "experiments/models/eval_omr_dln.py",
        "--images",
        image_arg,
        "--output-dir",
        detector._rel(omr_output),
        "--pre-computed-sr",
        detector._rel(sr_output / "batch"),
    ]
    env = os.environ.copy()
    homr_path = PROJECT_ROOT / "external" / "homr"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(PROJECT_ROOT), str(homr_path), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    run_with_logging(omr_cmd, env=env, check=True)

    omr_predictions = omr_output / stem / "predictions.json"
    if not omr_predictions.is_file():
        raise FileNotFoundError(omr_predictions)

    payload = {
        "schema_version": "pipeline.current_x4_support.v1",
        "status": "completed",
        "image": str(image),
        "sr_scale": sr_scale,
        "sr_image": str(sr_image),
        "current_sr_detection": str(current_sr_detection),
        "current_omr": str(omr_predictions),
        "support_root": str(output_root),
        "historical_detector_artifact_runtime_input": False,
        "commands": [omr_cmd],
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
