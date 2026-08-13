"""Generate fresh baseline-HOMR staff masks for Phase B MMR geometry.

This worker intentionally uses the current pipeline HOMR runtime and the same
in-process baseline producer that restored the accepted Issue #244 staff mask.
It does not feed any generated detections back into the detector route; only the
fresh staff-mask artifact is consumed by downstream MMR geometry reconstruction.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.pipeline.detection.hybrid import HybridDetector

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("MMR staff-geometry request must be a mapping")
    return dict(payload)


def run(request_path: Path, result_path: Path) -> Path:
    request = _load_request(request_path)
    det_cfg = request.get("detection")
    if not isinstance(det_cfg, Mapping):
        raise ValueError("MMR staff-geometry request lacks detection settings")

    raw_images = request.get("images")
    if not isinstance(raw_images, list) or not raw_images:
        raise ValueError("MMR staff-geometry request requires at least one image")

    images = [Path(str(value)).resolve() for value in raw_images]
    missing = [str(path) for path in images if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing MMR staff-geometry images: " + ", ".join(missing))

    stems = [path.stem for path in images]
    if len(stems) != len(set(stems)):
        raise ValueError("MMR staff-geometry generation requires unique image stems")

    output_root = Path(str(request["output_root"])).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    detector = HybridDetector(
        det_cfg=dict(det_cfg),
        images=images,
        run_id="mmr_staff_geometry",
        project_root=PROJECT_ROOT,
        dry_run=False,
        skip_existing=bool(request.get("skip_existing", False)),
        in_memory_images=None,
    )
    detector._run_homr_in_process(output_root, enable_sr=False)

    staff_masks: dict[str, str] = {}
    for image in images:
        staff_mask = output_root / "batch" / image.stem / f"{image.stem}_staff_mask.png"
        if not staff_mask.is_file():
            raise FileNotFoundError(staff_mask)
        staff_masks[str(image)] = str(staff_mask.resolve())

    payload = {
        "schema_version": "pipeline.mmr_staff_geometry.v1",
        "status": "completed",
        "producer": "HybridDetector._run_homr_in_process",
        "producer_runtime": "current_pipeline_homr",
        "historical_detector_artifact_runtime_input": False,
        "images": [str(path) for path in images],
        "staff_masks": staff_masks,
        "output_root": str(output_root),
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
