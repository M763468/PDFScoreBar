"""Execute one production detector page in a disposable Python process."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _load_request(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Detector page request must be a mapping")
    return dict(payload)


def run(request_path: Path, result_path: Path) -> Path:
    request = _load_request(request_path)
    config = request.get("config")
    if not isinstance(config, Mapping):
        raise ValueError("Detector page request lacks config")
    image = Path(str(request["image"])).resolve()
    page_id = str(request["page_id"])
    run_id = str(request["run_id"])
    run_dir = Path(str(request["run_dir"])).resolve()
    if not image.is_file():
        raise FileNotFoundError(image)

    # Import and patch the heavy detector only inside this disposable worker.
    # The package-level dispatcher intentionally leaves these imports out of the
    # long-lived parent process so the x4 SR peak has the same memory boundary as
    # the successful Issue #255 one-page reconstruction workers.
    from src.pipeline.detection.connector_artifacts import (
        install_homr_connector_artifact_capture,
        install_homr_skip_existing_guard,
    )

    install_homr_connector_artifact_capture()
    install_homr_skip_existing_guard()

    from src.pipeline.detection.restored_orchestrator import run_detection_step

    result = run_detection_step(
        dict(config),
        [image],
        [page_id],
        run_id,
        run_dir,
        dry_run=bool(request.get("dry_run", False)),
    )
    contract = result.get("detector_input_contract")
    if not isinstance(contract, Mapping):
        raise ValueError("Detector page result lacks input contract")

    payload = {
        "schema_version": "pipeline.detector_isolated_page.v1",
        "status": "completed",
        "image": str(image),
        "page_id": page_id,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "commands": result.get("commands", []),
        "hybrid_output_dir": str(result["hybrid_output_dir"]),
        "probe_output_dir": str(result["probe_output_dir"]),
        "detector_input_contract": dict(contract),
        "detector_route": result.get("detector_route"),
        "homr_profile": result.get("homr_profile"),
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
