"""Generate one two-HOMR detector source page in a disposable Python process."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .profile_hybrid_batch_sr import BatchSRVerifiedProfileHybridDetector


def _load_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Verified source-page request must be a mapping")
    return dict(payload)


def run(request_path: Path, result_path: Path) -> Path:
    request = _load_request(request_path)
    det_cfg = request.get("detection")
    if not isinstance(det_cfg, Mapping):
        raise ValueError("Verified source-page request lacks detection settings")

    image = Path(str(request["image"])).resolve()
    baseline_output = Path(str(request["baseline_output"])).resolve()
    support_output = Path(str(request["support_output"])).resolve()
    project_root = Path(str(request["project_root"])).resolve()
    profile_name = str(request["profile_name"])
    run_id = str(request["run_id"])
    precomputed_sr_raw = request.get("precomputed_sr")
    if precomputed_sr_raw is not None and not isinstance(precomputed_sr_raw, Mapping):
        raise ValueError("Verified source-page precomputed_sr must be a mapping")
    precomputed_sr = dict(precomputed_sr_raw) if precomputed_sr_raw is not None else None

    detector = BatchSRVerifiedProfileHybridDetector(
        det_cfg=dict(det_cfg),
        images=[image],
        run_id=run_id,
        project_root=project_root,
        dry_run=False,
        skip_existing=False,
        profile_name=profile_name,
    )
    payload = detector._generate_one_page_sources_in_process(
        image=image,
        baseline_output=baseline_output,
        support_output=support_output,
        precomputed_sr=precomputed_sr,
    )
    payload.update(
        {
            "schema_version": "pipeline.verified_source_page.v3",
            "status": "completed",
            "image": str(image),
            "memory_boundary": "top_level_python_per_page",
            "sr_execution_scope": (
                "dedicated_sr_batch_process" if precomputed_sr is not None else "page_subprocess"
            ),
            "historical_detector_artifact_runtime_input": False,
            "homr_neural_inference_count": 2,
            "x4_homr_neural_inference_count": 1,
        }
    )
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
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
